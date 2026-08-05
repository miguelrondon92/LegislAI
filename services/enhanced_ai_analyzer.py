import json
import os
import logging
from typing import Dict, List, Optional, Tuple, Any
import google.generativeai as genai
# from openai import OpenAI  # Removed - using Gemini only
import re
from datetime import datetime
from utils.constants import FEDERAL_POLICY_CATEGORIES, GEMINI_MODEL
from utils.bill_chunker import BillChunker, BillChunk
import time
import random

logger = logging.getLogger(__name__)

class AIAnalysisPartialError(Exception):
    """Exception raised when AI analysis is only partially completed due to rate limits"""
    def __init__(self, message, completion_percentage=0, completed_chunks=0, total_chunks=0):
        super().__init__(message)
        self.completion_percentage = completion_percentage
        self.completed_chunks = completed_chunks
        self.total_chunks = total_chunks

class EnhancedAIAnalyzer:
    """Enhanced AI-powered legislative analysis with hidden provision detection"""

    MODEL_NAME = GEMINI_MODEL
    
    def __init__(self):
        self.model_name = self.MODEL_NAME
        self.api_key = os.environ.get('GEMINI_API_KEY')
        if not self.api_key:
            logging.warning("GEMINI_API_KEY not found. AI analysis will be disabled.")
            self.client = None
            try:
                from services.ops_alert_service import (
                    CLIENT_UNAVAILABLE,
                    notify_gemini_failure,
                )
                notify_gemini_failure(
                    CLIENT_UNAVAILABLE,
                    "GEMINI_API_KEY not found. AI analysis will be disabled.",
                    severity="error",
                    source="analyzer",
                    provider_model=self.model_name,
                )
            except Exception:
                pass
        else:
            genai.configure(api_key=self.api_key)
            # gemini-1.5-flash is no longer available on many API keys; 2.0 is used elsewhere in repo
            self.client = genai.GenerativeModel(self.model_name)

        # Rate limiting — free-tier Gemini Flash-Lite: ~15 RPM, ~250k TPM, 1M context
        self.max_requests_per_minute = 15
        self.max_input_tokens_per_minute = 250_000
        self.usable_tpm_headroom = 220_000  # leave buffer under TPM
        self.max_tokens_per_request = 200_000  # per-request input cap (was stale 30k)
        self.tier_a_max_tokens = 150_000  # whole-bill single/two-pass below this
        self.macro_chunk_target_tokens = 120_000  # Tier B map chunk size
        self.estimated_tokens_per_char = 0.30  # dense legislative text
        self.max_budget_waits_per_analysis = 2
        self.max_chunks_per_bill = 50  # Tier B macro-chunk safety cap (not a shredding target)

        # Initialize bill chunker (macro sizing set per Tier B run)
        self.bill_chunker = BillChunker(max_chunk_size=6000, overlap_size=800)
        
        # Use the standardized federal policy categories
        self.policy_categories = FEDERAL_POLICY_CATEGORIES
        
        # Hidden provision detection patterns
        self.suspicious_patterns = [
            r'notwithstanding\s+any\s+other\s+provision\s+of\s+law',
            r'waiver\s+of\s+requirements',
            r'exemption\s+from\s+review',
            r'expedited\s+process',
            r'emergency\s+authority',
            r'discretionary\s+power',
            r'delegation\s+of\s+authority',
            r'confidential\s+information',
            r'classified\s+provisions',
            r'executive\s+privilege',
            r'national\s+security\s+exception',
            r'emergency\s+declaration',
            r'fast\s+track',
            r'expedited\s+approval',
            r'bypass\s+normal\s+procedures',
            r'override\s+existing\s+law',
            r'sunset\s+provision',
            r'grandfather\s+clause',
            r'retroactive\s+application',
            r'hidden\s+funding',
            r'earmark\s+disguised',
            r'policy\s+rider',
            r'unrelated\s+provision',
            r'last\s+minute\s+amendment',
            r'omnibus\s+provision',
            r'consolidated\s+appropriations',
            r'continuing\s+resolution\s+provision',
            r'budget\s+reconciliation\s+provision'
        ]
        
        # Add backoff configuration
        self.max_retries = 3
        self.base_delay = 1.0  # Start with 1 second
        self.max_delay = 60.0  # Max delay of 60 seconds
        self.backoff_multiplier = 2.0
        self.jitter_factor = 0.1  # Add 10% jitter
        
        # Request tracking for rate limiting (RPM + TPM)
        self.request_count = 0
        self.last_request_time = None
        self.requests_this_minute = 0
        self.tokens_this_minute = 0
        self.minute_start_time = None
        self._hit_gemini_api_429 = False
    
    def _ops_extra(self, **kwargs) -> Dict[str, Any]:
        """Build ops alert extra with model identity."""
        extra = {"provider_model": self.model_name, "model": self.model_name}
        extra.update(kwargs)
        return extra
    
    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text"""
        return int(len(text or "") * self.estimated_tokens_per_char)

    def _macro_chunk_max_chars(self) -> int:
        return max(1000, int(self.macro_chunk_target_tokens / self.estimated_tokens_per_char))

    def _reset_minute_window_if_needed(self):
        current_time = time.time()
        if not self.minute_start_time or current_time - self.minute_start_time >= 60:
            self.minute_start_time = current_time
            self.requests_this_minute = 0
            self.tokens_this_minute = 0

    def _check_rate_limit(self, estimated_tokens: int = 0) -> bool:
        """True if we cannot take another request (RPM or TPM)."""
        self._reset_minute_window_if_needed()

        if self.requests_this_minute >= self.max_requests_per_minute:
            logger.warning(
                f"🚫 RPM limit reached: {self.requests_this_minute}/{self.max_requests_per_minute}"
            )
            return True

        projected = self.tokens_this_minute + max(0, estimated_tokens)
        if projected > self.usable_tpm_headroom:
            logger.warning(
                f"🚫 TPM headroom reached: {self.tokens_this_minute}+{estimated_tokens} "
                f"> {self.usable_tpm_headroom}"
            )
            return True

        if self.requests_this_minute >= self.max_requests_per_minute - 2:
            logger.warning(
                f"⚠️ Near RPM limit: {self.requests_this_minute}/{self.max_requests_per_minute}"
            )

        return False

    def _record_request(self, estimated_tokens: int = 0):
        """Record a request for RPM+TPM limiting. Returns False if at limit."""
        self._reset_minute_window_if_needed()

        if self.requests_this_minute >= self.max_requests_per_minute:
            logger.error("🚫 Attempted to record request when already at RPM limit")
            return False
        if self.tokens_this_minute + max(0, estimated_tokens) > self.usable_tpm_headroom:
            logger.error("🚫 Attempted to record request when TPM headroom exhausted")
            return False

        self.requests_this_minute += 1
        self.tokens_this_minute += max(0, estimated_tokens)
        self.request_count += 1
        self.last_request_time = time.time()

        logger.debug(
            f"📊 Request recorded: {self.requests_this_minute}/{self.max_requests_per_minute} RPM, "
            f"{self.tokens_this_minute}/{self.usable_tpm_headroom} TPM"
        )
        return True

    def _wait_for_rate_limit(self, estimated_tokens: int = 0):
        """Wait if we're at rate limit (RPM or TPM)."""
        if self._check_rate_limit(estimated_tokens):
            wait_time = 60 - (time.time() - (self.minute_start_time or time.time()))
            if wait_time > 0:
                logger.info(f"⏳ Waiting {wait_time:.1f}s for rate limit reset...")
                time.sleep(wait_time)
            self.minute_start_time = time.time()
            self.requests_this_minute = 0
            self.tokens_this_minute = 0
    
    def analyze_bill(self, bill_or_text, title=None, allow_budget_waits=True) -> Dict:
        """Size-aware analysis: Tier A full-text two-pass, Tier B map-reduce + resume.

        allow_budget_waits: when True (offline/backfill), may sleep for local minute
        resets to expand a Tier B wave. UI async paths should pass False.
        """
        start_time = time.time()
        logger.info(f"[AI] Starting analysis for bill: {title}")
        self._allow_budget_waits = bool(allow_budget_waits)
        self._hit_gemini_api_429 = False

        if not self.client:
            logging.warning("Gemini client not available")
            try:
                from services.ops_alert_service import (
                    CLIENT_UNAVAILABLE,
                    notify_gemini_failure,
                )
                bill_obj = bill_or_text if hasattr(bill_or_text, "get_bill_identifier") else None
                notify_gemini_failure(
                    CLIENT_UNAVAILABLE,
                    "Gemini client not available",
                    severity="error",
                    bill=bill_obj,
                    source="analyzer",
                    provider_model=self.model_name,
                )
            except Exception:
                pass
            return {}

        try:
            bill = None
            if hasattr(bill_or_text, "get_bill_identifier"):
                bill = bill_or_text
                text_to_analyze = self._prepare_bill_text(bill)
                title = bill.title
                summary = bill.summary or ""
            else:
                text_to_analyze = str(bill_or_text)
                title = title or "Unknown Bill"
                summary = ""

            if not text_to_analyze:
                logging.warning("No text available for analysis")
                return {}

            prior = self._load_prior_partial(bill)
            total_chars = len(text_to_analyze)
            estimated_tokens = self._estimate_tokens(text_to_analyze)
            logger.info(
                f"[AI] Text length={total_chars:,} chars (~{estimated_tokens:,} tokens); "
                f"tier_a_max={self.tier_a_max_tokens:,}"
            )

            if estimated_tokens <= self.tier_a_max_tokens:
                analysis_results = self._analyze_tier_a(
                    text_to_analyze, title, summary, total_chars
                )
            else:
                analysis_results = self._analyze_tier_b(
                    text_to_analyze,
                    title,
                    summary,
                    total_chars,
                    prior_analysis=prior,
                    allow_budget_waits=self._allow_budget_waits,
                )

            if not analysis_results:
                return self._create_minimal_analysis(title, summary)

            # Risk + quota metadata
            analysis_results["overall_risk_score"] = self._calculate_overall_risk_score(
                analysis_results
            )
            analysis_results["quota_usage"] = {
                "requests_used": self.requests_this_minute,
                "tokens_used": self.tokens_this_minute,
                "analysis_was_limited_by_quota": bool(analysis_results.get("is_partial")),
                "limit_cause": analysis_results.get("limit_cause"),
            }
            analysis_results.setdefault("provider_model", self.model_name)
            analysis_results.setdefault("generated_at", datetime.now().isoformat())
            analysis_results.setdefault("hidden_detection_enabled", True)

            processing_time = time.time() - start_time
            self._persist_analysis_results(
                bill_or_text, analysis_results, processing_time
            )

            logger.info("[AI] Analysis completed successfully.")

            if hasattr(bill_or_text, "id") and analysis_results:
                try:
                    overall_risk_score = analysis_results.get("overall_risk_score", 0)
                    if overall_risk_score >= 0.7:
                        from services.notification_helper import (
                            trigger_high_risk_bill_notification,
                        )
                        trigger_high_risk_bill_notification(
                            bill_or_text.id, overall_risk_score
                        )
                except Exception as e:
                    logger.warning(f"Could not trigger high-risk notifications: {e}")

            if analysis_results.get("is_partial", False):
                self._raise_partial_error(bill_or_text, analysis_results)

            return analysis_results

        except AIAnalysisPartialError:
            raise
        except Exception as e:
            logger.error(f"[AI] Exception during analysis: {e}")
            try:
                from services.ops_alert_service import (
                    classify_gemini_error,
                    notify_gemini_failure,
                )
                bill_obj = bill_or_text if hasattr(bill_or_text, "get_bill_identifier") else None
                notify_gemini_failure(
                    classify_gemini_error(str(e)),
                    str(e),
                    severity="error",
                    bill=bill_obj,
                    source="analyzer",
                    provider_model=self.model_name,
                )
            except Exception:
                pass
            return {}

    def _load_prior_partial(self, bill) -> Optional[Dict]:
        if not bill or not hasattr(bill, "get_active_ai_analysis"):
            return None
        try:
            active = bill.get_active_ai_analysis()
            if not active:
                return None
            data = active.get_analysis_data() or {}
            if data.get("is_partial") and data.get("analysis_method") == "map_reduce_macro_chunks":
                return data
        except Exception as e:
            logger.debug(f"Could not load prior partial: {e}")
        return None

    def _analyze_tier_a(
        self, text: str, title: str, summary: str, total_chars: int
    ) -> Dict:
        """Two Gemini calls over full bill text — no chunking, never partial."""
        logger.info("[AI] Tier A: single-pass full-text (core + integrity)")
        categories_list = ", ".join(self.policy_categories)

        core_prompt = f"""Analyze this congressional bill. Focus on a clear summary and policy category labels.

Bill Title: {title}

Bill Text:
{text}

Return JSON with keys:
{{
  "summary": {{
    "main_summary": "clear summary",
    "key_provisions": ["..."],
    "funding_amounts": "string or Unknown",
    "implementation_timeline": "string or Unknown",
    "plain_language_explanation": "string"
  }},
  "policy_implications": {{
    "primary_category": "one of: {categories_list}",
    "secondary_categories": ["..."],
    "categories": [
      {{"area": "category name from the list", "impact_level": "high|medium|low", "reasoning": "one sentence"}}
    ],
    "primary_policy_area": "same as primary_category"
  }},
  "complexity_assessment": {{
    "complexity_score": 0.0,
    "reading_level": "string",
    "implementation_difficulty": "string",
    "scope_of_impact": "string",
    "estimated_cost_impact": "string",
    "regulatory_burden": "string",
    "urgency_level": "string",
    "complexity_factors": []
  }},
  "controversy_score": 0.0,
  "cross_references": {{
    "references_found": [],
    "assessment": "string"
  }}
}}
complexity_score and controversy_score must be floats from 0.0 to 1.0.
Use only policy categories from the provided list when possible.
Do NOT include stakeholders or a long policy narrative — those are separate passes.
"""

        integrity_prompt = f"""Analyze this congressional bill for hidden, sneaky, or buried provisions and risk language.

Bill Title: {title}

Bill Text:
{text}

Return JSON with keys:
{{
  "hidden_provisions": {{
    "detected_provisions": [
      {{
        "type": "string",
        "text": "string",
        "risk_level": "low|medium|high",
        "risk_factors": ["..."],
        "potential_impact": "string",
        "recommendation": "string",
        "confidence_score": 0.0,
        "chunk_index": 0,
        "chunk_type": "full_text"
      }}
    ],
    "suspicious_chunk_indices": [],
    "cross_chunk_analysis": null,
    "total_suspicious_chunks": 0,
    "overall_hidden_risk_score": 0.0
  }},
  "suspicious_language": {{
    "findings": [],
    "ai_analysis": {{"risk_score": 0.0, "assessment": "string"}}
  }},
  "anomalies": {{
    "anomalies_found": [],
    "assessment": "string"
  }},
  "hidden_impact_assessment": {{
    "economic_impact": "string",
    "social_impact": "string",
    "civil_liberties_impact": "string",
    "overall_assessment": "string"
  }}
}}
"""

        core = self._call_ai_json(core_prompt) or {}
        integrity = self._call_ai_json(integrity_prompt) or {}

        results: Dict[str, Any] = {}
        if isinstance(core.get("summary"), dict):
            results["summary"] = core["summary"]
        elif isinstance(core.get("summary"), str):
            results["summary"] = {
                "main_summary": core["summary"],
                "key_provisions": [],
                "funding_amounts": "Unknown",
                "implementation_timeline": "Unknown",
                "plain_language_explanation": core["summary"],
            }
        if isinstance(core.get("policy_implications"), dict):
            results["policy_implications"] = core["policy_implications"]
        if isinstance(core.get("complexity_assessment"), dict):
            results["complexity_assessment"] = core["complexity_assessment"]
        if isinstance(core.get("controversy_score"), (int, float)):
            results["controversy_score"] = float(core["controversy_score"])
        if isinstance(core.get("cross_references"), dict):
            results["cross_references"] = core["cross_references"]

        for key in (
            "hidden_provisions",
            "suspicious_language",
            "anomalies",
            "hidden_impact_assessment",
        ):
            if isinstance(integrity.get(key), dict):
                results[key] = integrity[key]

        from services.analysis_enrichers import (
            attach_policy_areas,
            pending_enrichment_stubs,
        )

        results.update(pending_enrichment_stubs())
        results = attach_policy_areas(results)
        results["enrichments_needed"] = True

        results.update(
            {
                "analysis_method": "single_pass_full_text",
                "analysis_tier": "A",
                "is_partial": False,
                "completion_percentage": 100.0,
                "chars_analyzed": total_chars,
                "total_chars": total_chars,
                "chunks_analyzed": 1,
                "total_chunks_available": 1,
                "remaining_chunks": 0,
                "analyzed_chunk_keys": ["full_text"],
                "analysis_completeness": "full",
                "limit_cause": None,
                "provider_model": self.model_name,
            }
        )
        return results

    def _analyze_tier_b(
        self,
        text: str,
        title: str,
        summary: str,
        total_chars: int,
        prior_analysis: Optional[Dict] = None,
        allow_budget_waits: bool = True,
    ) -> Dict:
        """Map-reduce over macro-chunks with cumulative resume."""
        logger.info("[AI] Tier B: map-reduce macro-chunks")
        max_chars = self._macro_chunk_max_chars()
        macros = self.bill_chunker.build_macro_chunks(text, max_chars=max_chars)
        if len(macros) > self.max_chunks_per_bill:
            logger.warning(
                f"Capping macro-chunks {len(macros)} → {self.max_chunks_per_bill} "
                "(document order preserved)"
            )
            macros = macros[: self.max_chunks_per_bill]

        prior_keys = set((prior_analysis or {}).get("analyzed_chunk_keys") or [])
        remaining = self.bill_chunker.filter_unanalyzed(macros, prior_keys)

        if not remaining:
            logger.info("[AI] Tier B: no remaining macro-chunks — marking complete")
            merged = dict(prior_analysis or {})
            merged.update(
                {
                    "is_partial": False,
                    "completion_percentage": 100.0,
                    "remaining_chunks": 0,
                    "chars_analyzed": total_chars,
                    "total_chars": total_chars,
                    "analysis_completeness": "full",
                    "limit_cause": None,
                    "analysis_method": "map_reduce_macro_chunks",
                    "analysis_tier": "B",
                    "provider_model": self.model_name,
                }
            )
            return merged

        wave = self._select_tier_b_wave(remaining, allow_budget_waits=allow_budget_waits)
        if not wave:
            minimal = self._create_minimal_analysis(title, summary)
            minimal.update(
                {
                    "analysis_method": "map_reduce_macro_chunks",
                    "analysis_tier": "B",
                    "is_partial": True,
                    "completion_percentage": self._char_completion(
                        prior_keys, macros, total_chars
                    ),
                    "analyzed_chunk_keys": sorted(prior_keys),
                    "chunks_analyzed": len(prior_keys),
                    "total_chunks_available": len(macros),
                    "remaining_chunks": len(remaining),
                    "chars_analyzed": self._chars_for_keys(prior_keys, macros),
                    "total_chars": total_chars,
                    "limit_cause": "local_minute_budget",
                }
            )
            return minimal

        map_findings = []
        newly_done = []
        for i, chunk in enumerate(wave):
            finding = self._map_macro_chunk(chunk, title, i)
            if finding is not None:
                map_findings.append(finding)
            newly_done.append(chunk.ensure_key())

        all_keys = prior_keys | set(newly_done)
        prior_maps = list((prior_analysis or {}).get("tier_b_map_findings") or [])
        combined_maps = prior_maps + map_findings

        is_complete = len(all_keys) >= len(macros)
        if is_complete:
            results = self._reduce_tier_b(combined_maps, title, text)
        else:
            results = self._merge_partial_tier_b(prior_analysis, combined_maps, title)

        chars_done = self._chars_for_keys(all_keys, macros)
        completion = min(100.0, (chars_done / total_chars) * 100.0) if total_chars else 100.0
        limit_cause = (
            "gemini_api_429"
            if self._hit_gemini_api_429
            else ("local_minute_budget" if not is_complete else None)
        )

        results.update(
            {
                "analysis_method": "map_reduce_macro_chunks",
                "analysis_tier": "B",
                "is_partial": not is_complete,
                "completion_percentage": 100.0 if is_complete else completion,
                "chars_analyzed": total_chars if is_complete else chars_done,
                "total_chars": total_chars,
                "chunks_analyzed": len(all_keys),
                "total_chunks_available": len(macros),
                "remaining_chunks": max(0, len(macros) - len(all_keys)),
                "analyzed_chunk_keys": sorted(all_keys),
                "tier_b_map_findings": combined_maps,
                "analysis_completeness": "full" if is_complete else "partial",
                "limit_cause": limit_cause,
                "provider_model": self.model_name,
            }
        )
        if is_complete:
            from services.analysis_enrichers import (
                attach_policy_areas,
                pending_enrichment_stubs,
            )

            stubs = pending_enrichment_stubs()
            if not isinstance(results.get("policy_analysis"), dict):
                results["policy_analysis"] = stubs["policy_analysis"]
            if not isinstance(results.get("stakeholders"), dict) or results[
                "stakeholders"
            ].get("status") not in ("ready", "pending", "skipped"):
                results["stakeholders"] = stubs["stakeholders"]
            results = attach_policy_areas(results)
            results["enrichments_needed"] = True
        return results

    def _select_tier_b_wave(
        self, remaining: List[BillChunk], allow_budget_waits: bool = True
    ) -> List[BillChunk]:
        """Pick as many remaining macro-chunks as RPM+TPM allow this wave (dry-run)."""
        selected: List[BillChunk] = []
        waits = 0
        max_waits = self.max_budget_waits_per_analysis if allow_budget_waits else 0
        pending = list(remaining)

        while pending:
            self._reset_minute_window_if_needed()
            sim_rpm = self.requests_this_minute
            sim_tpm = self.tokens_this_minute
            # Reserve 1 RPM for reduce / buffer when finishing
            rpm_cap = self.max_requests_per_minute - 1
            added_this_pass = 0
            still = []

            for chunk in pending:
                tokens = self._estimate_tokens(chunk.content) + 1500
                if sim_rpm + 1 > rpm_cap or sim_tpm + tokens > self.usable_tpm_headroom:
                    still.append(chunk)
                    continue
                selected.append(chunk)
                sim_rpm += 1
                sim_tpm += tokens
                added_this_pass += 1

            pending = still
            if added_this_pass == 0:
                if waits >= max_waits:
                    break
                self._wait_for_rate_limit_reset()
                waits += 1
                continue
            if not allow_budget_waits or not pending or waits >= max_waits:
                break
            self._wait_for_rate_limit_reset()
            waits += 1

        return selected

    def _map_macro_chunk(self, chunk: BillChunk, title: str, index: int) -> Optional[Dict]:
        prompt = f"""Analyze this portion of a congressional bill (map step).

Bill Title: {title}
Chunk key: {chunk.ensure_key()}
Chunk index: {index}
Chunk type: {chunk.chunk_type}

Text:
{chunk.content}

Return JSON:
{{
  "chunk_key": "{chunk.ensure_key()}",
  "summary": "brief summary of this portion",
  "key_provisions": ["..."],
  "policy_areas": ["..."],
  "stakeholders": ["..."],
  "hidden_provisions": [
    {{
      "type": "string",
      "text": "string",
      "risk_level": "low|medium|high",
      "confidence_score": 0.0
    }}
  ],
  "suspicious_language": [],
  "cross_references": [],
  "complexity_notes": "string",
  "controversy_notes": "string"
}}
"""
        result = self._call_ai_json(prompt)
        if not result:
            return {
                "chunk_key": chunk.ensure_key(),
                "summary": "",
                "key_provisions": [],
                "policy_areas": [],
                "stakeholders": [],
                "hidden_provisions": [],
                "map_failed": True,
            }
        result["chunk_key"] = chunk.ensure_key()
        return result

    def _reduce_tier_b(self, map_findings: List[Dict], title: str, full_text: str) -> Dict:
        categories_list = ", ".join(self.policy_categories)
        findings_blob = json.dumps(map_findings, indent=2)[:120000]
        prompt = f"""You are consolidating mapped analyses of bill portions into one final analysis.

Bill Title: {title}

Mapped portion findings (JSON):
{findings_blob}

Return a single JSON object with:
{{
  "summary": {{
    "main_summary": "...",
    "key_provisions": [],
    "funding_amounts": "Unknown",
    "implementation_timeline": "Unknown",
    "plain_language_explanation": "..."
  }},
  "policy_implications": {{
    "primary_category": "from: {categories_list}",
    "secondary_categories": [],
    "categories": [{{"area": "...", "impact_level": "high|medium|low", "reasoning": "..."}}],
    "primary_policy_area": "..."
  }},
  "stakeholders": {{
    "winners": [],
    "losers": [],
    "neutral_parties": [],
    "key_interest_groups": []
  }},
  "complexity_assessment": {{
    "complexity_score": 0.0,
    "reading_level": "Unknown",
    "implementation_difficulty": "Unknown",
    "scope_of_impact": "Unknown",
    "estimated_cost_impact": "Unknown",
    "regulatory_burden": "Unknown",
    "urgency_level": "Unknown",
    "complexity_factors": []
  }},
  "controversy_score": 0.0,
  "hidden_provisions": {{
    "detected_provisions": [],
    "suspicious_chunk_indices": [],
    "cross_chunk_analysis": null,
    "total_suspicious_chunks": 0,
    "overall_hidden_risk_score": 0.0
  }},
  "suspicious_language": {{"findings": [], "ai_analysis": {{"risk_score": 0.0}}}},
  "anomalies": {{"anomalies_found": [], "assessment": ""}},
  "cross_references": {{"references_found": [], "assessment": ""}},
  "hidden_impact_assessment": {{
    "economic_impact": "",
    "social_impact": "",
    "civil_liberties_impact": "",
    "overall_assessment": ""
  }}
}}
"""
        reduced = self._call_ai_json(prompt) or {}
        return reduced if isinstance(reduced, dict) else {}

    def _merge_partial_tier_b(
        self, prior: Optional[Dict], map_findings: List[Dict], title: str
    ) -> Dict:
        """Build a usable partial payload without requiring a reduce call."""
        base = dict(prior or {})
        summaries = [m.get("summary") for m in map_findings if m.get("summary")]
        provisions = []
        for m in map_findings:
            provisions.extend(m.get("key_provisions") or [])
        hidden = []
        for m in map_findings:
            for hp in m.get("hidden_provisions") or []:
                if isinstance(hp, dict):
                    hidden.append(hp)

        prior_summary = ((prior or {}).get("summary") or {}).get("main_summary", "")
        combined_summary = prior_summary
        if summaries:
            extra = " ".join(summaries[:5])
            combined_summary = (prior_summary + " " + extra).strip() if prior_summary else extra

        base["summary"] = {
            "main_summary": combined_summary or f"Partial analysis of {title}",
            "key_provisions": provisions[:20],
            "funding_amounts": ((prior or {}).get("summary") or {}).get(
                "funding_amounts", "Unknown"
            ),
            "implementation_timeline": ((prior or {}).get("summary") or {}).get(
                "implementation_timeline", "Unknown"
            ),
            "plain_language_explanation": combined_summary
            or f"Partial analysis of {title}",
        }

        prior_hidden = ((prior or {}).get("hidden_provisions") or {}).get(
            "detected_provisions", []
        )
        all_hidden = list(prior_hidden) + hidden
        base["hidden_provisions"] = {
            "detected_provisions": all_hidden,
            "suspicious_chunk_indices": [],
            "cross_chunk_analysis": None,
            "total_suspicious_chunks": len(all_hidden),
            "overall_hidden_risk_score": self._calculate_hidden_risk_score(all_hidden)
            if all_hidden
            else 0.0,
        }
        if "policy_implications" not in base:
            base["policy_implications"] = {
                "primary_category": "Government Operations",
                "secondary_categories": [],
                "categories": [],
                "primary_policy_area": "Government Operations",
            }
        return base

    def _chars_for_keys(self, keys, macros: List[BillChunk]) -> int:
        keyset = set(keys or [])
        return sum(len(c.content) for c in macros if c.ensure_key() in keyset)

    def _char_completion(self, keys, macros: List[BillChunk], total_chars: int) -> float:
        if not total_chars:
            return 100.0
        return min(100.0, (self._chars_for_keys(keys, macros) / total_chars) * 100.0)

    def _persist_analysis_results(
        self, bill_or_text, analysis_results: Dict, processing_time: float
    ) -> None:
        if not analysis_results:
            return
        if hasattr(bill_or_text, "create_new_analysis_version"):
            try:
                complexity_assessment = analysis_results.get("complexity_assessment", {})
                complexity_score = None
                if isinstance(complexity_assessment, dict):
                    complexity_score = complexity_assessment.get("complexity_score")
                controversy_score = analysis_results.get("controversy_score", 0.0)
                if not isinstance(controversy_score, (int, float)):
                    controversy_score = 0.0

                chunks_analyzed = analysis_results.get("chunks_analyzed", 0)
                method = analysis_results.get("analysis_method", "chunked")

                bill_or_text.create_new_analysis_version(
                    analysis_data=analysis_results,
                    complexity_score=complexity_score,
                    controversy_score=controversy_score,
                    analysis_method=method,
                    chunks_analyzed=chunks_analyzed,
                    processing_time=processing_time,
                    provider_model=self.model_name,
                )

                summary_data = analysis_results.get("summary", {})
                if isinstance(summary_data, dict):
                    bill_or_text.create_new_summary_version(
                        summary_text=summary_data.get("main_summary"),
                        plain_language_summary=summary_data.get(
                            "plain_language_explanation"
                        ),
                        key_provisions=summary_data.get("key_provisions", []),
                        funding_amounts=summary_data.get("funding_amounts"),
                        implementation_timeline=summary_data.get(
                            "implementation_timeline"
                        ),
                        summary_type="ai_generated",
                        provider_model=self.model_name,
                    )

                if "policy_implications" in analysis_results:
                    policy_data = analysis_results["policy_implications"]
                    if isinstance(policy_data.get("categories"), list):
                        self._store_policy_categories(
                            bill_or_text, policy_data["categories"], analysis_results
                        )

                if hasattr(bill_or_text, "update_display_ready_status"):
                    status_changed = bill_or_text.update_display_ready_status()
                    if status_changed and hasattr(bill_or_text, "id"):
                        try:
                            from services.notification_helper import (
                                trigger_bill_analysis_notification_async,
                            )
                            trigger_bill_analysis_notification_async(bill_or_text.id)
                        except Exception as e:
                            logger.warning(f"Could not trigger notifications: {e}")
            except Exception as e:
                logger.error(f"Error creating new database structure: {e}")
        elif hasattr(bill_or_text, "set_ai_analysis"):
            bill_or_text.set_ai_analysis(analysis_results)
            if "policy_implications" in analysis_results:
                policy_data = analysis_results["policy_implications"]
                if isinstance(policy_data.get("categories"), list):
                    self._store_policy_categories(
                        bill_or_text, policy_data["categories"], analysis_results
                    )
            if hasattr(bill_or_text, "update_display_ready_status"):
                bill_or_text.update_display_ready_status()

    def _raise_partial_error(self, bill_or_text, analysis_results: Dict) -> None:
        completion_percentage = analysis_results.get("completion_percentage", 0)
        remaining_chunks = analysis_results.get("remaining_chunks", 0)
        completed_chunks = analysis_results.get("chunks_analyzed", 0)
        total_chunks = analysis_results.get("total_chunks_available", 0)
        limit_cause = analysis_results.get("limit_cause") or "local_minute_budget"
        partial_msg = (
            f"Bill analysis was only {completion_percentage:.1f}% complete "
            f"(model={self.model_name}, chunks={completed_chunks}/{total_chunks}, "
            f"chars={analysis_results.get('chars_analyzed', 0)}/"
            f"{analysis_results.get('total_chars', 0)}, "
            f"limit_cause={limit_cause}). {remaining_chunks} chunks remaining."
        )
        try:
            from services.ops_alert_service import (
                PARTIAL_ANALYSIS,
                notify_gemini_failure,
            )
            bill_obj = bill_or_text if hasattr(bill_or_text, "get_bill_identifier") else None
            notify_gemini_failure(
                PARTIAL_ANALYSIS,
                partial_msg,
                severity="warning",
                bill=bill_obj,
                completion_percentage=completion_percentage,
                provider_model=self.model_name,
                source="analyzer",
                extra=self._ops_extra(
                    completed_chunks=completed_chunks,
                    total_chunks=total_chunks,
                    limit_cause=limit_cause,
                    chunks=f"{completed_chunks}/{total_chunks}",
                    chars_analyzed=analysis_results.get("chars_analyzed"),
                    total_chars=analysis_results.get("total_chars"),
                    analysis_tier=analysis_results.get("analysis_tier"),
                ),
            )
        except Exception:
            pass
        raise AIAnalysisPartialError(
            partial_msg,
            completion_percentage=completion_percentage,
            completed_chunks=completed_chunks,
            total_chunks=total_chunks,
        )

    def _call_ai_json(self, prompt: str) -> Optional[Dict]:
        """Call Gemini expecting JSON; returns parsed dict or None."""
        text = self._call_ai_model(prompt, expect_json=True)
        if text is None:
            return None
        if isinstance(text, dict):
            return text
        if isinstance(text, str):
            try:
                return json.loads(self._clean_json_response(text))
            except json.JSONDecodeError:
                logging.warning("Failed to parse JSON from model response")
                return None
        return None

    def _detect_hidden_provisions(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:

        """Detect potentially hidden or sneaky provisions in bill chunks"""
        try:
            if not self.client:
                return None
            
            # Analyze each chunk for hidden provisions
            hidden_provisions = []
            suspicious_chunks = []
            
            for i, chunk in enumerate(chunks):
                chunk_analysis = self._analyze_chunk_for_hidden_provisions(chunk, i, title)
                if chunk_analysis and isinstance(chunk_analysis, dict):
                    hidden_provisions.append(chunk_analysis)
                    if chunk_analysis.get('risk_level', 'low') in ['medium', 'high']:
                        suspicious_chunks.append(i)
            
            # Cross-reference analysis between chunks
            cross_chunk_analysis = self._cross_reference_chunks_for_hidden_provisions(chunks, suspicious_chunks)
            
            return {
                'detected_provisions': hidden_provisions,
                'suspicious_chunk_indices': suspicious_chunks,
                'cross_chunk_analysis': cross_chunk_analysis,
                'total_suspicious_chunks': len(suspicious_chunks),
                'overall_hidden_risk_score': self._calculate_hidden_risk_score(hidden_provisions)
            }
            
        except Exception as e:
            logging.error(f"Hidden provision detection error: {str(e)}")
            return None
    
    def _analyze_chunk_for_hidden_provisions(self, chunk: BillChunk, chunk_index: int, title: str) -> Optional[Dict]:
        """Analyze a single chunk for hidden provisions"""
        try:
            prompt = f"""
            Analyze this bill chunk for potentially hidden, sneaky, or buried provisions that might not be immediately obvious.
            
            Bill Title: {title}
            Chunk Type: {chunk.chunk_type}
            Chunk Index: {chunk_index}
            
            Bill Content:
            {chunk.content[:3000]}
            
            Look for:
            1. Provisions that seem unrelated to the main bill purpose
            2. Language that grants broad discretionary powers
            3. Exemptions or waivers that bypass normal procedures
            4. Funding provisions that seem hidden or disguised
            5. Policy riders that don't relate to the main bill
            6. Provisions that limit oversight or review
            7. Retroactive applications or grandfather clauses
            8. Emergency authorities or expedited processes
            9. Confidentiality or classification provisions
            10. Delegations of authority that seem excessive
            
            Respond in JSON format:
            {{
                "risk_level": "low|medium|high",
                "suspicious_provisions": [
                    {{
                        "type": "description of provision type",
                        "text": "exact text or description",
                        "risk_factors": ["list of risk factors"],
                        "potential_impact": "description of potential impact",
                        "recommendation": "what to watch for"
                    }}
                ],
                "overall_assessment": "brief assessment of this chunk",
                "confidence_score": 0.0-1.0
            }}
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                return None
            
            # Clean and parse JSON response
            cleaned_response = self._clean_json_response(response_text)
            try:
                result = json.loads(cleaned_response)
                result['chunk_index'] = chunk_index
                result['chunk_type'] = chunk.chunk_type
                return result
            except json.JSONDecodeError:
                logging.warning(f"Failed to parse hidden provision analysis for chunk {chunk_index}")
                return None
                
        except Exception as e:
            logging.error(f"Chunk hidden provision analysis error: {str(e)}")
            return None
    
    def _cross_reference_chunks_for_hidden_provisions(self, chunks: List[BillChunk], suspicious_chunks: List[int]) -> Optional[Dict]:
        """Cross-reference chunks to find hidden provisions that span multiple sections"""
        try:
            if len(suspicious_chunks) < 2:
                return None
            
            # Get suspicious chunk contents
            suspicious_contents = []
            for idx in suspicious_chunks:
                if idx < len(chunks):
                    suspicious_contents.append(f"Chunk {idx} ({chunks[idx].chunk_type}): {chunks[idx].content[:1500]}")
            
            combined_content = "\n\n---\n\n".join(suspicious_contents)
            
            prompt = f"""
            Analyze these suspicious bill chunks together to identify hidden provisions that might span multiple sections or be connected across chunks.
            
            Suspicious Chunks Content:
            {combined_content}
            
            Look for:
            1. Provisions that reference each other across chunks
            2. Hidden funding that's split across multiple sections
            3. Policy changes that are implemented piecemeal across chunks
            4. Oversight limitations that are distributed across sections
            5. Emergency authorities that build upon each other
            6. Delegations that compound across multiple provisions
            
            Respond in JSON format:
            {{
                "cross_chunk_provisions": [
                    {{
                        "provision_type": "description",
                        "involved_chunks": [chunk_indices],
                        "combined_impact": "description",
                        "risk_level": "low|medium|high",
                        "detection_difficulty": "easy|medium|hard"
                    }}
                ],
                "overall_pattern": "description of any overall pattern",
                "recommendations": ["list of recommendations"]
            }}
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                return None
            
            cleaned_response = self._clean_json_response(response_text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse cross-chunk analysis")
                return None
                
        except Exception as e:
            logging.error(f"Cross-reference analysis error: {str(e)}")
            return None
    
    def _detect_anomalies(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Detect anomalies in bill structure and content"""
        try:
            if not self.client:
                return None
            
            # Analyze chunk patterns and content for anomalies
            chunk_summaries = []
            for i, chunk in enumerate(chunks):
                chunk_summaries.append(f"Chunk {i}: Type={chunk.chunk_type}, Length={len(chunk.content)}, Score={chunk.importance_score}")
            
            chunk_info = "\n".join(chunk_summaries)
            
            prompt = f"""
            Analyze this bill's chunk structure and content for anomalies that might indicate hidden provisions or unusual legislative tactics.
            
            Bill Title: {title}
            Number of Chunks: {len(chunks)}
            
            Chunk Information:
            {chunk_info}
            
            Look for anomalies such as:
            1. Unusually long or short chunks
            2. Chunks with very high or low importance scores
            3. Unusual distribution of content types
            4. Chunks that seem out of place
            5. Patterns that suggest rushed or last-minute additions
            6. Unusual language complexity variations
            7. Inconsistent formatting or structure
            
            Respond in JSON format:
            {{
                "detected_anomalies": [
                    {{
                        "type": "anomaly type",
                        "description": "description",
                        "affected_chunks": [chunk_indices],
                        "significance": "low|medium|high",
                        "potential_implications": "description"
                    }}
                ],
                "overall_anomaly_score": 0.0-1.0,
                "recommendations": ["list of recommendations"]
            }}
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                return None
            
            cleaned_response = self._clean_json_response(response_text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse anomaly detection")
                return None
                
        except Exception as e:
            logging.error(f"Anomaly detection error: {str(e)}")
            return None
    
    def _detect_suspicious_language(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Detect suspicious language patterns using regex and AI analysis"""
        try:
            suspicious_findings = []
            
            # Pattern-based detection
            for i, chunk in enumerate(chunks):
                chunk_findings = {
                    'chunk_index': i,
                    'chunk_type': chunk.chunk_type,
                    'pattern_matches': [],
                    'ai_analysis': None
                }
                
                # Check for suspicious patterns
                for pattern in self.suspicious_patterns:
                    matches = re.findall(pattern, chunk.content, re.IGNORECASE)
                    if matches:
                        chunk_findings['pattern_matches'].append({
                            'pattern': pattern,
                            'matches': matches,
                            'context': self._get_context_around_matches(chunk.content, pattern)
                        })
                
                if chunk_findings['pattern_matches']:
                    suspicious_findings.append(chunk_findings)
            
            # AI-based suspicious language analysis
            if self.client and suspicious_findings:
                ai_analysis = self._ai_analyze_suspicious_language(chunks, suspicious_findings, title)
                return {
                    'pattern_based_findings': suspicious_findings,
                    'ai_analysis': ai_analysis,
                    'total_suspicious_chunks': len(suspicious_findings)
                }
            
            return {
                'pattern_based_findings': suspicious_findings,
                'ai_analysis': None,
                'total_suspicious_chunks': len(suspicious_findings)
            }
            
        except Exception as e:
            logging.error(f"Suspicious language detection error: {str(e)}")
            return None
    
    def _ai_analyze_suspicious_language(self, chunks: List[BillChunk], suspicious_findings: List[Dict], title: str) -> Optional[Dict]:
        """Use AI to analyze suspicious language patterns"""
        try:
            # Get suspicious chunks for AI analysis
            suspicious_chunks = []
            for finding in suspicious_findings:
                chunk_idx = finding['chunk_index']
                if chunk_idx < len(chunks):
                    suspicious_chunks.append(f"Chunk {chunk_idx}: {chunks[chunk_idx].content[:2000]}")
            
            combined_content = "\n\n---\n\n".join(suspicious_chunks)
            
            prompt = f"""
            Analyze these bill chunks that contain suspicious language patterns for potential hidden provisions or concerning legislative tactics.
            
            Bill Title: {title}
            
            Suspicious Content:
            {combined_content}
            
            Analyze for:
            1. Hidden policy changes disguised in technical language
            2. Broad discretionary powers that could be misused
            3. Provisions that bypass normal oversight
            4. Funding mechanisms that hide true costs
            5. Emergency authorities that seem excessive
            6. Provisions that limit transparency or accountability
            
            Respond in JSON format:
            {{
                "suspicious_provisions": [
                    {{
                        "type": "provision type",
                        "risk_level": "low|medium|high",
                        "description": "description",
                        "potential_abuse": "how it could be abused",
                        "recommendation": "what to watch for"
                    }}
                ],
                "overall_assessment": "overall assessment",
                "risk_score": 0.0-1.0
            }}
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                return None
            
            cleaned_response = self._clean_json_response(response_text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse AI suspicious language analysis")
                return None
                
        except Exception as e:
            logging.error(f"AI suspicious language analysis error: {str(e)}")
            return None
    
    def _get_context_around_matches(self, text: str, pattern: str, context_chars: int = 200) -> List[str]:
        """Get context around pattern matches"""
        contexts = []
        for match in re.finditer(pattern, text, re.IGNORECASE):
            start = max(0, match.start() - context_chars)
            end = min(len(text), match.end() + context_chars)
            context = text[start:end]
            contexts.append(context)
        return contexts
    
    def _analyze_cross_references(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Analyze cross-references between bill sections and external laws"""
        try:
            if not self.client:
                return None
            
            # Extract potential cross-references
            cross_ref_patterns = [
                r'section\s+\d+',
                r'title\s+\d+',
                r'chapter\s+\d+',
                r'act\s+of\s+\d{4}',
                r'public\s+law\s+\d+-\d+',
                r'usc\s+\d+',
                r'cfr\s+\d+',
                r'amends\s+section',
                r'repeals\s+section',
                r'references\s+section'
            ]
            
            cross_refs = []
            for i, chunk in enumerate(chunks):
                chunk_refs = []
                for pattern in cross_ref_patterns:
                    matches = re.findall(pattern, chunk.content, re.IGNORECASE)
                    if matches:
                        chunk_refs.extend(matches)
                
                if chunk_refs:
                    cross_refs.append({
                        'chunk_index': i,
                        'chunk_type': chunk.chunk_type,
                        'references': chunk_refs
                    })
            
            if not cross_refs:
                return None
            
            # AI analysis of cross-references
            ref_content = []
            for ref in cross_refs:
                chunk_idx = ref['chunk_index']
                if chunk_idx < len(chunks):
                    ref_content.append(f"Chunk {chunk_idx}: {chunks[chunk_idx].content[:1500]}")
            
            combined_content = "\n\n---\n\n".join(ref_content)
            
            prompt = f"""
            Analyze these bill chunks that contain cross-references to other laws and regulations for potential hidden provisions or concerning changes.
            
            Bill Title: {title}
            
            Content with Cross-References:
            {combined_content}
            
            Look for:
            1. References that modify existing laws in unexpected ways
            2. Cross-references that grant new authorities
            3. Amendments that are buried in technical language
            4. Repeals of important provisions
            5. References that bypass normal legislative procedures
            6. Changes to unrelated laws through this bill
            
            Respond in JSON format:
            {{
                "concerning_references": [
                    {{
                        "reference_type": "type of reference",
                        "potential_impact": "description",
                        "risk_level": "low|medium|high",
                        "recommendation": "what to investigate"
                    }}
                ],
                "overall_assessment": "overall assessment",
                "recommendations": ["list of recommendations"]
            }}
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                return None
            
            cleaned_response = self._clean_json_response(response_text)
            try:
                result = json.loads(cleaned_response)
                result['cross_references_found'] = cross_refs
                return result
            except json.JSONDecodeError:
                logging.warning("Failed to parse cross-reference analysis")
                return None
                
        except Exception as e:
            logging.error(f"Cross-reference analysis error: {str(e)}")
            return None
    
    def _assess_hidden_impact(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Assess the potential impact of hidden provisions"""
        try:
            if not self.client:
                return None
            
            # Use important chunks for impact assessment
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i} ({chunk.chunk_type}): {chunk.content[:2000]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Assess the potential impact of any hidden or buried provisions in this bill.
            
            Bill Title: {title}
            
            Bill Content (from important chunks):
            {combined_text}
            
            Assess for:
            1. Economic impact of hidden provisions
            2. Social and community impact
            3. Environmental impact
            4. Impact on civil liberties and rights
            5. Impact on government transparency
            6. Impact on oversight and accountability
            7. Long-term consequences
            8. Unintended consequences
            
            Respond in JSON format:
            {{
                "impact_assessment": {{
                    "economic_impact": "description",
                    "social_impact": "description", 
                    "environmental_impact": "description",
                    "civil_liberties_impact": "description",
                    "transparency_impact": "description",
                    "oversight_impact": "description",
                    "long_term_consequences": "description",
                    "unintended_consequences": "description"
                }},
                "overall_impact_score": 0.0-1.0,
                "risk_factors": ["list of risk factors"],
                "recommendations": ["list of recommendations"]
            }}
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                return None
            
            cleaned_response = self._clean_json_response(response_text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse hidden impact assessment")
                return None
                
        except Exception as e:
            logging.error(f"Hidden impact assessment error: {str(e)}")
            return None
    
    def _calculate_hidden_risk_score(self, hidden_provisions: List[Dict]) -> float:
        """Calculate overall risk score for hidden provisions"""
        if not hidden_provisions:
            return 0.0
        
        risk_scores = []
        for provision in hidden_provisions:
            if provision and isinstance(provision, dict):
                risk_level = provision.get('risk_level', 'low')
                confidence = provision.get('confidence_score', 0.5)
                
                risk_value = {
                    'low': 0.2,
                    'medium': 0.5,
                    'high': 0.8
                }.get(risk_level, 0.2)
                
                risk_scores.append(risk_value * confidence)
        
        return sum(risk_scores) / len(risk_scores) if risk_scores else 0.0
    
    def _calculate_overall_risk_score(self, analysis_results: Dict) -> float:
        """Calculate overall risk score combining all analysis components"""
        risk_factors = []
        
        # Hidden provisions risk
        if 'hidden_provisions' in analysis_results:
            hidden_prov_data = analysis_results['hidden_provisions']
            if hidden_prov_data and isinstance(hidden_prov_data, dict):
                hidden_risk = hidden_prov_data.get('overall_hidden_risk_score', 0.0)
                risk_factors.append(hidden_risk * 0.4)  # 40% weight
        
        # Anomalies risk
        if 'anomalies' in analysis_results:
            anomalies_data = analysis_results['anomalies']
            if anomalies_data and isinstance(anomalies_data, dict):
                anomaly_risk = anomalies_data.get('overall_anomaly_score', 0.0)
                risk_factors.append(anomaly_risk * 0.2)  # 20% weight
        
        # Suspicious language risk
        if 'suspicious_language' in analysis_results:
            suspicious_lang_data = analysis_results['suspicious_language']
            if suspicious_lang_data and isinstance(suspicious_lang_data, dict):
                ai_analysis = suspicious_lang_data.get('ai_analysis', {})
                if ai_analysis and isinstance(ai_analysis, dict):
                    suspicious_risk = ai_analysis.get('risk_score', 0.0)
                    risk_factors.append(suspicious_risk * 0.2)  # 20% weight
        
        # Controversy risk
        if 'controversy_score' in analysis_results:
            controversy_risk = analysis_results['controversy_score']
            risk_factors.append(controversy_risk * 0.1)  # 10% weight
        
        # Complexity risk
        if 'complexity_assessment' in analysis_results:
            complexity_risk = analysis_results['complexity_assessment'].get('complexity_score', 0.0)
            risk_factors.append(complexity_risk * 0.1)  # 10% weight
        
        return sum(risk_factors) if risk_factors else 0.0
    
    # Include all the standard analysis methods from the original AIAnalyzer
    def _prepare_bill_text(self, bill) -> str:
        """Prepare bill text for analysis — prefer persisted full_text (no re-fetch)."""
        text_parts = []
        
        if bill.title:
            text_parts.append(f"Title: {bill.title}")
        
        if bill.summary:
            text_parts.append(f"Summary: {bill.summary}")
        
        # Prefer column, then get_full_text (which persists on miss)
        full_text = getattr(bill, "full_text", None) or bill.get_full_text()
        if full_text:
            text_parts.append(f"Full Text: {full_text}")
        
        return "\n\n".join(text_parts)
    
    def _generate_bill_summary_chunked(self, chunks: List[BillChunk], title: str) -> Optional[str]:
        """Generate bill summary using chunked analysis"""
        try:
            if not self.client:
                return None
            
            # Use the most important chunks for summary
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:3]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:2000]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Create a comprehensive summary of this congressional bill based on the following chunks.
            
            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Please provide a clear, comprehensive summary that:
            1. Explains what the bill does in simple terms
            2. Highlights the main changes it would make
            3. Mentions who would be affected
            4. Notes any significant funding or timeline requirements
            
            Keep it concise but comprehensive, suitable for someone without legal expertise.
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                logging.warning("Empty response from Gemini for summary")
                return None
            
            return response_text.strip()
            
        except Exception as e:
            logging.error(f"Chunked summary generation error: {str(e)}")
            return None
    
    def _categorize_bill_chunked(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Categorize bill into policy domains using chunked analysis"""
        try:
            if not self.client:
                return None
                
            categories_list = ', '.join(self.policy_categories)
            
            # Use the most important chunks for categorization
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_header = f"Chunk {i+1} ({chunk.chunk_type})"
                if hasattr(chunk, 'section_title') and chunk.section_title:
                    chunk_header += f" - {chunk.section_title}"
                if hasattr(chunk, 'section_number') and chunk.section_number:
                    chunk_header += f" (Section {chunk.section_number})"
                chunk_texts.append(f"{chunk_header}:\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Categorize this congressional bill into the most relevant policy domains from the following list:
            {categories_list}
            
            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Respond in JSON format with categories and confidence scores:
            {{
                "primary_category": "most relevant category",
                "secondary_categories": ["list of other relevant categories"],
                "category_breakdown": {{
                    "category_name": {{
                        "relevance_score": 0.0-1.0,
                        "reasoning": "why this category is relevant",
                        "section": "section number if applicable",
                        "title": "section title if applicable"
                    }}
                }},
                "overall_assessment": "brief assessment of bill's policy focus"
            }}
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                logging.warning("Empty response from Gemini for categorization")
                return None
            
            # Clean and parse JSON response
            cleaned_response = self._clean_json_response(response_text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse categorization response")
                return None
                
        except Exception as e:
            logging.error(f"Chunked categorization error: {str(e)}")
            return None
    
    def _analyze_stakeholders_chunked(self, chunks: List[BillChunk], title: str) -> Optional[Dict]:
        """Analyze stakeholders using chunked analysis"""
        try:
            if not self.client:
                return None
            
            # Use the most important chunks for stakeholder analysis
            important_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)[:5]
            
            chunk_texts = []
            for i, chunk in enumerate(important_chunks):
                chunk_texts.append(f"Chunk {i+1} ({chunk.chunk_type}):\n{chunk.content[:1500]}")
            
            combined_text = "\n\n---\n\n".join(chunk_texts)
            
            prompt = f"""
            Analyze the stakeholders affected by this congressional bill.
            
            Bill Title: {title}
            
            Bill Content (from {len(important_chunks)} key chunks):
            {combined_text}
            
            Identify and analyze:
            1. Direct beneficiaries
            2. Groups that may be negatively affected
            3. Industry stakeholders
            4. Government agencies involved
            5. Geographic regions affected
            6. Economic sectors impacted
            
            Respond in JSON format:
            {{
                "stakeholders": {{
                    "beneficiaries": ["list of beneficiaries"],
                    "negatively_affected": ["list of negatively affected groups"],
                    "industry_stakeholders": ["list of industry stakeholders"],
                    "government_agencies": ["list of government agencies"],
                    "geographic_regions": ["list of affected regions"],
                    "economic_sectors": ["list of affected sectors"]
                }},
                "impact_assessment": "overall assessment of stakeholder impacts",
                "key_considerations": ["list of key considerations"]
            }}
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                logging.warning("Empty response from Gemini for stakeholder analysis")
                return None
            
            # Clean and parse JSON response
            cleaned_response = self._clean_json_response(response_text)
            try:
                return json.loads(cleaned_response)
            except json.JSONDecodeError:
                logging.warning("Failed to parse stakeholder analysis response")
                return None
                
        except Exception as e:
            logging.error(f"Chunked stakeholder analysis error: {str(e)}")
            return None
    
    def _clean_json_response(self, response_text: str) -> str:
        """Clean and extract JSON from AI response"""
        # Remove markdown code blocks
        response_text = re.sub(r'```json\s*', '', response_text)
        response_text = re.sub(r'```\s*$', '', response_text)
        
        # Find JSON object
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if json_match:
            return json_match.group()
        
        return response_text.strip()
    
    def _assess_complexity(self, bill_text: str) -> Optional[float]:
        """Assess bill complexity"""
        try:
            if not self.client:
                logger.warning("Complexity assessment: No Gemini client available")
                return None
            
            # Check if we're at rate limit and wait if needed
            if self._check_rate_limit():
                logger.warning("Complexity assessment: Rate limit reached, waiting for reset...")
                self._wait_for_rate_limit()
                logger.info("Complexity assessment: Rate limit reset, proceeding")
            
            # Use a sample of the text for complexity assessment
            sample_text = bill_text[:5000] if len(bill_text) > 5000 else bill_text
            
            prompt = f"""
            Assess the complexity of this congressional bill on a scale of 0.0 to 1.0, where 0.0 is very simple and 1.0 is extremely complex.
            
            Bill Text Sample:
            {sample_text}
            
            Consider factors like:
            - Technical language and jargon
            - Number of cross-references
            - Length and scope
            - Implementation complexity
            - Regulatory requirements
            
            Respond with only a number between 0.0 and 1.0.
            """

            logger.debug("Complexity assessment: Making Gemini API call")
            response_text = self._call_ai_model(prompt)

            if not response_text:
                logger.warning("Complexity assessment: Empty response text from Gemini")
                return None
            
            # Extract numeric response
            try:
                response_text = response_text.strip()
                logger.debug(f"Complexity assessment: Raw response: '{response_text}'")
                complexity_score = float(response_text)
                clamped_score = max(0.0, min(1.0, complexity_score))  # Clamp between 0 and 1
                logger.info(f"Complexity assessment: Success - score: {clamped_score}")
                return clamped_score
            except ValueError as ve:
                logger.error(f"Complexity assessment: Failed to parse response '{response_text}': {ve}")
                return None
                
        except Exception as e:
            logger.error(f"Complexity assessment error: {str(e)}")
            return None
    
    def _detect_controversy(self, bill_text: str, title: str) -> Optional[float]:
        """Detect controversy level"""
        try:
            if not self.client:
                return None
            
            # Use a sample of the text for controversy detection
            sample_text = bill_text[:5000] if len(bill_text) > 5000 else bill_text
            
            prompt = f"""
            Assess the potential controversy level of this congressional bill on a scale of 0.0 to 1.0, where 0.0 is uncontroversial and 1.0 is highly controversial.
            
            Bill Title: {title}
            Bill Text Sample:
            {sample_text}
            
            Consider factors like:
            - Polarizing policy positions
            - Impact on civil liberties
            - Economic implications
            - Social and cultural implications
            - Partisan implications
            
            Respond with only a number between 0.0 and 1.0.
            """
            
            response_text = self._call_ai_model(prompt)
            
            if not response_text:
                return None
            
            # Extract numeric response
            try:
                controversy_score = float(response_text.strip())
                return max(0.0, min(1.0, controversy_score))  # Clamp between 0 and 1
            except ValueError:
                return None
                
        except Exception as e:
            logging.error(f"Controversy detection error: {str(e)}")
            return None
    
    def calculate_alignment_score(self, user_preferences: Dict, bill_categories: Dict) -> float:
        """Calculate alignment between user preferences and bill categories"""
        try:
            if not user_preferences or not bill_categories:
                return 0.0
            
            # Extract user's preferred categories
            user_categories = user_preferences.get('policy_categories', [])
            if not user_categories:
                return 0.0
            
            # Extract bill's primary and secondary categories
            bill_primary = bill_categories.get('primary_category', '')
            bill_secondary = bill_categories.get('secondary_categories', [])
            
            # Calculate alignment score
            alignment_score = 0.0
            total_weight = 0.0
            
            # Primary category gets higher weight
            if bill_primary in user_categories:
                alignment_score += 0.7
                total_weight += 0.7
            
            # Secondary categories get lower weight
            for category in bill_secondary:
                if category in user_categories:
                    alignment_score += 0.3
                    total_weight += 0.3
            
            # Normalize score
            if total_weight > 0:
                return alignment_score / total_weight
            
            return 0.0
            
        except Exception as e:
            logging.error(f"Alignment score calculation error: {str(e)}")
            return 0.0

    def _call_ai_model(self, prompt, expect_json: bool = False):
        """Call Gemini with RPM+TPM accounting. Returns text, parsed dict (if expect_json), or None."""
        logger.debug(f"[AI] Calling model with prompt length: {len(prompt)}")

        estimated_tokens = self._estimate_tokens(prompt)
        logger.debug(f"[AI] Estimated tokens: {estimated_tokens:,}")

        self._wait_for_rate_limit(estimated_tokens)

        if estimated_tokens > self.max_tokens_per_request:
            logger.warning(
                f"⚠️ Request too large: {estimated_tokens:,} tokens "
                f"(limit: {self.max_tokens_per_request:,}) — attempting anyway with headroom check"
            )

        generation_config = None
        if expect_json:
            try:
                generation_config = genai.types.GenerationConfig(
                    response_mime_type="application/json"
                )
            except Exception:
                generation_config = {"response_mime_type": "application/json"}

        for attempt in range(self.max_retries + 1):
            try:
                if self._check_rate_limit(estimated_tokens):
                    logger.error(f"🚫 Rate limit check failed on attempt {attempt + 1}")
                    return None

                if not self._record_request(estimated_tokens):
                    logger.error(
                        f"🚫 Failed to record request due to rate limit on attempt {attempt + 1}"
                    )
                    return None

                if generation_config is not None:
                    response = self.client.generate_content(
                        prompt, generation_config=generation_config
                    )
                else:
                    response = self.client.generate_content(prompt)

                logger.debug(f"[AI] Model raw API response: {str(response)[:2000]}... (truncated)")

                if hasattr(response, "error") and response.error:
                    logger.error(f"[AI] Model error: {response.error}")
                    if hasattr(response.error, "code") and response.error.code == 429:
                        self._hit_gemini_api_429 = True
                        if attempt < self.max_retries:
                            delay = self._calculate_backoff_delay(attempt)
                            logger.warning(
                                f"[AI] Rate limited (429). Attempt {attempt + 1}/"
                                f"{self.max_retries + 1}. Waiting {delay:.1f}s..."
                            )
                            time.sleep(delay)
                            continue
                        return None
                    return None

                text = getattr(response, "text", None) or ""
                if not text:
                    return None

                if expect_json:
                    try:
                        return json.loads(self._clean_json_response(text))
                    except json.JSONDecodeError:
                        logging.warning("JSON parse failed after structured response")
                        return None
                return text

            except Exception as e:
                logger.error(f"[AI] Exception during model call (attempt {attempt + 1}): {e}")
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    self._hit_gemini_api_429 = True
                    if attempt < self.max_retries:
                        delay = self._calculate_backoff_delay(attempt)
                        logger.warning(
                            f"[AI] Rate limited (429) via exception. Attempt {attempt + 1}/"
                            f"{self.max_retries + 1}. Waiting {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        continue
                    return None
                return None

        return None
    
    def _calculate_backoff_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        # Exponential backoff: base_delay * (multiplier ^ attempt)
        delay = min(self.base_delay * (self.backoff_multiplier ** attempt), self.max_delay)
        
        # Add jitter to prevent thundering herd
        jitter = delay * self.jitter_factor * random.uniform(-1, 1)
        delay += jitter
        
        return max(0.1, delay)  # Ensure minimum delay of 0.1 seconds
    
    def get_rate_limit_status(self) -> Dict:
        """Get current rate limiting status"""
        self._reset_minute_window_if_needed()
        current_time = time.time()

        time_until_reset = 0
        if self.minute_start_time:
            time_until_reset = max(0, 60 - (current_time - self.minute_start_time))

        remaining_requests = max(0, self.max_requests_per_minute - self.requests_this_minute)
        remaining_tokens = max(0, self.usable_tpm_headroom - self.tokens_this_minute)

        return {
            'requests_this_minute': self.requests_this_minute,
            'max_requests_per_minute': self.max_requests_per_minute,
            'remaining_requests': remaining_requests,
            'tokens_this_minute': self.tokens_this_minute,
            'max_input_tokens_per_minute': self.max_input_tokens_per_minute,
            'usable_tpm_headroom': self.usable_tpm_headroom,
            'remaining_tokens': remaining_tokens,
            'total_requests': self.request_count,
            'time_until_reset': time_until_reset,
            'is_at_limit': (
                self.requests_this_minute >= self.max_requests_per_minute
                or self.tokens_this_minute >= self.usable_tpm_headroom
            ),
            'is_approaching_limit': self.requests_this_minute >= self.max_requests_per_minute - 2,
            'last_request_time': self.last_request_time,
            'rate_limit_percentage': (self.requests_this_minute / self.max_requests_per_minute) * 100,
            'safe_remaining_requests': max(0, remaining_requests - 2),
        }

    def get_quota_info(self) -> Dict:
        """Get detailed quota information for planning"""
        status = self.get_rate_limit_status()

        return {
            'current_usage': {
                'requests_this_minute': status['requests_this_minute'],
                'max_requests_per_minute': status['max_requests_per_minute'],
                'remaining_requests': status['remaining_requests'],
                'safe_remaining_requests': status['safe_remaining_requests'],
                'percentage_used': status['rate_limit_percentage'],
                'tokens_this_minute': status['tokens_this_minute'],
                'remaining_tokens': status['remaining_tokens'],
            },
            'limits': {
                'max_chunks_per_bill': self.max_chunks_per_bill,
                'max_tokens_per_request': self.max_tokens_per_request,
                'max_requests_per_minute': self.max_requests_per_minute,
                'max_input_tokens_per_minute': self.max_input_tokens_per_minute,
                'tier_a_max_tokens': self.tier_a_max_tokens,
            },
            'timing': {
                'time_until_reset': status['time_until_reset'],
                'last_request_time': status['last_request_time']
            },
            'status': {
                'is_at_limit': status['is_at_limit'],
                'is_approaching_limit': status['is_approaching_limit'],
                # Tier A needs ~2 requests; keep names for routes compatibility
                'can_handle_large_bill': status['safe_remaining_requests'] >= 3,
                'can_handle_small_bill': status['safe_remaining_requests'] >= 2,
            }
        }

    def reset_rate_limit_counters(self):
        """Reset rate limit counters (useful for testing or manual reset)"""
        self.requests_this_minute = 0
        self.tokens_this_minute = 0
        self.minute_start_time = time.time()
        self.request_count = 0
        self.last_request_time = None
        logger.info("✅ Rate limit counters reset")
    
    def _estimate_analysis_requests(self, chunks: List[BillChunk]) -> int:
        """Estimate how many API requests will be needed for analysis"""
        # Each chunk typically needs multiple analysis types
        requests_per_chunk = 5  # Hidden provisions, summary, categories, stakeholders, etc.
        base_requests = len(chunks) * requests_per_chunk
        
        # Add requests for cross-chunk analysis
        cross_chunk_requests = max(1, len(chunks) // 3)  # Cross-reference analysis
        
        # Add requests for overall analysis
        overall_requests = 3  # Final summary, risk assessment, etc.
        
        total_requests = base_requests + cross_chunk_requests + overall_requests
        
        logger.debug(f"📊 Request estimation: {len(chunks)} chunks × {requests_per_chunk} + {cross_chunk_requests} cross-chunk + {overall_requests} overall = {total_requests}")
        
        return total_requests
    
    def _can_handle_analysis(self, estimated_requests: int) -> bool:
        """Check if we have enough API quota to handle this analysis"""
        remaining_requests = self.max_requests_per_minute - self.requests_this_minute
        
        # Add safety margin (leave 2 requests buffer)
        safe_remaining = max(0, remaining_requests - 2)
        
        can_handle = estimated_requests <= safe_remaining
        
        if not can_handle:
            logger.warning(f"⚠️ Analysis requires {estimated_requests} requests but only {safe_remaining} available")
            logger.warning(f"   Current usage: {self.requests_this_minute}/{self.max_requests_per_minute}")
            logger.warning(f"   Rate limit resets in {self.get_rate_limit_status()['time_until_reset']:.1f} seconds")
        
        return can_handle
    
    def _calculate_analyzable_chunks(self, chunks: List[BillChunk], available_requests: int) -> List[BillChunk]:
        """Calculate how many chunks we can analyze with available API quota"""
        if available_requests <= 2:  # Keep 2 requests as buffer
            logger.warning(f"⚠️ Insufficient quota ({available_requests}), no chunks can be analyzed")
            return []
        
        # Reserve requests for overall analysis (summary, final assessment)
        reserved_requests = 3
        usable_requests = max(0, available_requests - reserved_requests)
        
        # Each chunk needs approximately 5 requests for full analysis
        requests_per_chunk = 5
        max_chunks = max(0, usable_requests // requests_per_chunk)
        
        if max_chunks == 0:
            logger.warning(f"⚠️ Not enough quota for full chunk analysis. Available: {available_requests}, need minimum: {requests_per_chunk + reserved_requests}")
            return []
        
        # Sort chunks by importance and take the most important ones
        sorted_chunks = sorted(chunks, key=lambda x: x.importance_score, reverse=True)
        chunks_to_analyze = sorted_chunks[:max_chunks]
        
        logger.info(f"📊 Progressive Analysis: Analyzing {len(chunks_to_analyze)}/{len(chunks)} chunks with {usable_requests} available requests")
        if len(chunks_to_analyze) < len(chunks):
            logger.warning(f"⚠️ Partial analysis: {len(chunks) - len(chunks_to_analyze)} chunks will be skipped due to quota limits")
        
        return chunks_to_analyze

    def _expand_analyzable_chunks(
        self,
        chunks: List[BillChunk],
        available_requests: int,
        allow_budget_waits: bool = True,
    ) -> List[BillChunk]:
        """
        Select analyzable chunks, waiting up to max_budget_waits_per_analysis
        local-minute resets so one analyze_bill call can cover more than a
        single minute's progressive budget (when allow_budget_waits is True).
        """
        selected = self._calculate_analyzable_chunks(chunks, available_requests)
        if not selected or len(selected) >= len(chunks):
            return selected

        if not allow_budget_waits:
            return selected

        selected_ids = {id(c) for c in selected}
        budget_waits_used = 0
        max_waits = getattr(self, "max_budget_waits_per_analysis", 2)

        while len(selected) < len(chunks) and budget_waits_used < max_waits:
            remaining = [c for c in chunks if id(c) not in selected_ids]
            if not remaining:
                break

            logger.info(
                f"⏳ Local minute budget exhausted for batch "
                f"({len(selected)}/{len(chunks)} chunks); waiting for reset "
                f"({budget_waits_used + 1}/{max_waits}) to continue same-call analysis..."
            )
            self._wait_for_rate_limit_reset()
            budget_waits_used += 1

            next_available = self.max_requests_per_minute - self.requests_this_minute
            additional = self._calculate_analyzable_chunks(remaining, next_available)
            if not additional:
                break

            for chunk in additional:
                if id(chunk) not in selected_ids:
                    selected.append(chunk)
                    selected_ids.add(id(chunk))

            logger.info(
                f"📊 Expanded progressive batch to {len(selected)}/{len(chunks)} "
                f"chunks after {budget_waits_used} local-minute wait(s)"
            )

        return selected
    
    def _wait_for_rate_limit_reset(self):
        """Wait for rate limit to reset and log progress"""
        if not self.minute_start_time:
            return
        
        current_time = time.time()
        elapsed = current_time - self.minute_start_time
        wait_time = max(0, 60 - elapsed)
        
        if wait_time > 0:
            logger.info(f"⏳ Waiting {wait_time:.1f} seconds for rate limit reset...")
            logger.info(f"   Current usage: {self.requests_this_minute}/{self.max_requests_per_minute}")
            logger.info(f"   This ensures continued analysis rather than stopping completely")
            
            # Wait in smaller increments to show progress
            while wait_time > 0:
                sleep_time = min(10, wait_time)  # Sleep max 10 seconds at a time
                time.sleep(sleep_time)
                wait_time -= sleep_time
                if wait_time > 0:
                    logger.info(f"   Still waiting... {wait_time:.1f} seconds remaining")
            
            # Reset rate limit counters
            self.requests_this_minute = 0
            self.tokens_this_minute = 0
            self.minute_start_time = time.time()
            logger.info(f"✅ Rate limit reset complete, ready to continue analysis")
    
    def _create_minimal_analysis(self, title: str, summary: str) -> Dict:
        """Create minimal analysis when quota is insufficient for full analysis"""
        logger.info("📝 Creating minimal analysis due to quota constraints...")
        
        minimal_analysis = {
            'analysis_type': 'minimal',
            'analysis_method': 'minimal',
            'analysis_tier': 'C',
            'reason': 'insufficient_api_quota',
            'title': title,
            'summary': {
                'main_summary': summary if summary else 'No summary available',
                'key_provisions': [],
                'funding_amounts': 'Unknown',
                'implementation_timeline': 'Unknown',
                'plain_language_explanation': summary if summary else 'No summary available',
            },
            'analysis_completeness': 'partial',
            'is_partial': True,
            'completion_percentage': 0.0,
            'analyzed_sections': 'title_and_summary_only',
            'recommendation': 'Run full analysis when API quota is available',
            'provider_model': self.model_name,
            'limit_cause': 'local_minute_budget',
        }
        
        # Add basic pattern-based analysis without AI
        if title and summary:
            combined_text = f"{title} {summary}".lower()
            basic_flags = []
            
            # Check for basic suspicious patterns
            suspicious_keywords = ['emergency', 'waiver', 'notwithstanding', 'discretionary', 'classified']
            for keyword in suspicious_keywords:
                if keyword in combined_text:
                    basic_flags.append(keyword)
            
            if basic_flags:
                minimal_analysis['basic_flags'] = basic_flags
                minimal_analysis['requires_attention'] = True
            else:
                minimal_analysis['requires_attention'] = False
        
        logger.info("✅ Minimal analysis created - partial information available")
        return minimal_analysis

    def _parse_response(self, response):
        logger.debug(f"[AI] Parsing response: {str(response)[:2000]}... (truncated)")
        try:
            # Assume response is a dict or has a .text/.content attribute
            if hasattr(response, 'text'):
                raw = response_text
            elif hasattr(response, 'content'):
                raw = response.content
            else:
                raw = str(response)
            logger.debug(f"[AI] Raw text/content to parse: {raw[:2000]}... (truncated)")
            # Try to parse as JSON
            import json
            try:
                parsed = json.loads(raw)
                logger.debug(f"[AI] Parsed JSON: {str(parsed)[:1000]}... (truncated)")
                return parsed
            except Exception as json_err:
                logger.error(f"[AI] JSON parse error: {json_err}")
                # Fallback: try eval or return raw
                return None
        except Exception as e:
            logger.error(f"[AI] Exception during response parsing: {e}")
            return None
    
    def generate_user_specific_analysis(self, bill_analysis, user_preferences, alignment_score):
        """Generate personalized analysis based on user preferences"""
        try:
            # Create a summary of user preferences
            strong_preferences = []
            for area, prefs in user_preferences.items():
                if isinstance(prefs, dict) and prefs.get('importance') == 'high':
                    stance = prefs.get('stance', 'neutral')
                    if stance != 'neutral':
                        strong_preferences.append(f"{area}: {stance}")
            
            prompt = f"""
            Based on this bill analysis and user preferences, provide personalized insights.
            
            Bill Analysis Summary: {bill_analysis.get('summary', {}).get('main_summary', '')}
            Policy Areas: {bill_analysis.get('policy_implications', {}).get('primary_policy_area', '')}
            
            User's Strong Preferences: {'; '.join(strong_preferences)}
            Calculated Alignment Score: {alignment_score}
            
            Provide personalized analysis in JSON format:
            {{
                "personal_impact": "How this bill might personally affect someone with these preferences",
                "key_concerns": ["specific concerns based on user preferences"],
                "potential_benefits": ["potential benefits for this user"],
                "action_recommendations": ["what actions the user might consider taking"],
                "explanation_of_score": "Why the alignment score is what it is"
            }}
            """
            result = self._call_ai_model(prompt, expect_json=True)
            if result and isinstance(result, dict):
                return result
            return {
                "personal_impact": "Unable to generate personalized analysis",
                "key_concerns": [],
                "potential_benefits": [],
                "action_recommendations": [],
                "explanation_of_score": "Analysis unavailable due to technical error"
            }
        except Exception as e:
            logging.error(f"Error generating user-specific analysis: {str(e)}")
            return {
                "personal_impact": "Unable to generate personalized analysis",
                "key_concerns": [],
                "potential_benefits": [],
                "action_recommendations": [],
                "explanation_of_score": "Analysis unavailable due to technical error"
            }
    
    def _store_policy_categories(self, bill, categories, analysis=None):
        """Store policy category mappings for the bill, including sneakiness score per category"""
        try:
            # Import here to avoid circular imports
            from db_models import BillCategoryMapping, PolicyCategory, db
            import re
            import json
            
            if not hasattr(bill, 'id') or not bill.id:
                logger.error(f"Bill object has no ID, cannot store categories")
                return
            
            categories_stored = 0
            
            # Prepare sneakiness mapping if analysis is provided
            sneakiness_by_category = {}
            if analysis and 'hidden_provisions' in analysis:
                hidden_provisions = analysis['hidden_provisions'].get('detected_provisions', [])
                # Build a mapping: category_name -> max sneakiness score
                for provision in hidden_provisions:
                    provision_text = (provision.get('text') or '') + ' ' + (provision.get('type') or '')
                    risk_level = provision.get('risk_level', 'low')
                    confidence = provision.get('confidence_score', 0.5)
                    risk_value = {'low': 0.2, 'medium': 0.5, 'high': 0.8}.get(risk_level, 0.2)
                    sneakiness_score = risk_value * confidence
                    for cat in categories:
                        area = cat.get('area', '')
                        if area and re.search(re.escape(area), provision_text, re.IGNORECASE):
                            prev = sneakiness_by_category.get(area, 0.0)
                            sneakiness_by_category[area] = max(prev, sneakiness_score)
            
            for category_data in categories:
                try:
                    area = category_data.get('area', '').strip()
                    if not area:
                        continue
                    
                    # Get or create policy category
                    policy_category = PolicyCategory.query.filter_by(name=area).first()
                    if not policy_category:
                        policy_category = PolicyCategory(
                            name=area,
                            display_name=area,
                            description=f"Policy category for {area}",
                            is_active=True
                        )
                        db.session.add(policy_category)
                        db.session.flush()
                        logger.info(f"Created new policy category: {area}")
                    
                    # Check if mapping already exists
                    mapping = BillCategoryMapping.query.filter_by(
                        bill_id=bill.id,
                        policy_category_id=policy_category.id
                    ).first()
                    
                    # Extract relevance score from category data or use default
                    relevance_score = category_data.get('impact_level', 'medium')
                    if relevance_score == 'high':
                        score = 0.9
                    elif relevance_score == 'medium':
                        score = 0.7
                    elif relevance_score == 'low':
                        score = 0.5
                    else:
                        score = 0.7  # Default to medium
                    
                    # Get sneakiness score for this category
                    sneakiness_score = sneakiness_by_category.get(area, 0.0)
                    
                    # Build section reference
                    section_reference = category_data.get('section', '')
                    if section_reference and category_data.get('title'):
                        section_reference = f"{section_reference}: {category_data['title'][:100]}"
                    elif category_data.get('title'):
                        section_reference = category_data['title'][:150]
                    
                    if not mapping:
                        mapping = BillCategoryMapping(
                            bill_id=bill.id,
                            policy_category_id=policy_category.id,
                            relevance_score=score,
                            category_specific_analysis=json.dumps(category_data),
                            sneakiness_score=sneakiness_score,
                            section_reference=section_reference
                        )
                        db.session.add(mapping)
                        categories_stored += 1
                        logger.info(f"Created category mapping: {bill.get_bill_identifier()} -> {area} (score: {score}, sneakiness: {sneakiness_score})")
                    else:
                        mapping.category_specific_analysis = json.dumps(category_data)
                        mapping.sneakiness_score = sneakiness_score
                        mapping.section_reference = section_reference
                        logger.info(f"Updated existing category mapping: {bill.get_bill_identifier()} -> {area} (sneakiness: {sneakiness_score})")
                        
                except Exception as category_error:
                    logger.error(f"Error processing category '{area}': {category_error}")
                    continue
            
            if categories_stored > 0:
                db.session.commit()
                logger.info(f"Successfully stored {categories_stored} policy category mappings for {bill.get_bill_identifier()}")
            else:
                logger.warning(f"No new policy category mappings were stored for {bill.get_bill_identifier()}")
                
        except Exception as e:
            logger.error(f"Error storing policy categories for {bill.get_bill_identifier()}: {e}")
            if 'db' in locals():
                db.session.rollback() 