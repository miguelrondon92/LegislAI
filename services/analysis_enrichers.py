"""
Async downstream Gemini enrichments: stakeholders + deep policy analysis.

Runs after core Tier A/B analysis when local RPM/TPM allows.
Merges into a new AIAnalysis version; does not block display_ready.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, Optional

from utils.constants import GEMINI_MODEL

logger = logging.getLogger(__name__)


def pending_enrichment_stubs() -> Dict[str, Any]:
    """Initial stubs attached to core analysis_data before enrichers run."""
    return {
        "policy_analysis": {
            "status": "pending",
            "overall_assessment": None,
            "category_breakdown": {},
            "controversial_aspects": [],
            "bipartisan_potential": None,
        },
        "stakeholders": {
            "status": "pending",
            "affected_groups": [],
            "winners_losers": {
                "potential_winners": [],
                "potential_losers": [],
                "neutral_parties": [],
            },
            "geographic_impact": None,
        },
    }


def attach_policy_areas(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure policy_areas badges exist from policy_implications."""
    out = dict(analysis or {})
    pi = out.get("policy_implications") or {}
    if not isinstance(pi, dict):
        pi = {}
    primary = pi.get("primary_category") or pi.get("primary_policy_area")
    secondary = pi.get("secondary_categories") or []
    if not isinstance(secondary, list):
        secondary = []
    out["policy_areas"] = {
        "primary_category": primary,
        "secondary_categories": list(secondary),
    }
    return out


def enrichments_need_work(analysis: Optional[Dict[str, Any]]) -> bool:
    if not analysis:
        return False
    pa = analysis.get("policy_analysis") or {}
    st = analysis.get("stakeholders") or {}
    pa_status = pa.get("status") if isinstance(pa, dict) else None
    st_status = st.get("status") if isinstance(st, dict) else None
    if pa_status == "ready" and st_status == "ready":
        return False
    # Missing stubs, pending, or previously skipped (retry when quota recovers)
    return pa_status in (None, "pending", "skipped") or st_status in (
        None,
        "pending",
        "skipped",
    )


def enrichment_quota_ok(analyzer) -> tuple:
    """
    Whether ~2 Gemini calls are available for stakeholder + policy enrichers.

    Uses real remaining_requests (not the mis-nested get_quota_info status key).
    Returns (ok, remaining_requests, time_until_reset).
    """
    remaining = 0
    reset_in = 0.0
    if hasattr(analyzer, "get_rate_limit_status"):
        status = analyzer.get_rate_limit_status() or {}
        remaining = int(status.get("remaining_requests") or 0)
        reset_in = float(status.get("time_until_reset") or 0)
    else:
        quota = analyzer.get_quota_info() if hasattr(analyzer, "get_quota_info") else {}
        usage = (quota or {}).get("current_usage") or {}
        remaining = int(
            usage.get("remaining_requests")
            if usage.get("remaining_requests") is not None
            else usage.get("safe_remaining_requests") or 0
        )
        timing = (quota or {}).get("timing") or {}
        reset_in = float(timing.get("time_until_reset") or 0)
    return remaining >= 2, remaining, reset_in


def _normalize_stakeholders(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Map various Gemini shapes into template-canonical stakeholders."""
    if not isinstance(raw, dict):
        raw = {}

    affected = raw.get("affected_groups")
    if not isinstance(affected, list):
        affected = []
    # Promote flat winners/losers into affected_groups if needed
    if not affected:
        for label, impact in (
            ("winners", "positive"),
            ("losers", "negative"),
            ("neutral_parties", "neutral"),
            ("key_interest_groups", "neutral"),
            ("beneficiaries", "positive"),
            ("negatively_affected", "negative"),
        ):
            for item in raw.get(label) or []:
                if isinstance(item, str):
                    affected.append(
                        {
                            "group": item,
                            "impact_type": impact,
                            "impact_description": item,
                        }
                    )
                elif isinstance(item, dict) and item.get("group"):
                    affected.append(item)

    wl = raw.get("winners_losers")
    if not isinstance(wl, dict):
        wl = {}
    winners = wl.get("potential_winners") or raw.get("winners") or raw.get("beneficiaries") or []
    losers = wl.get("potential_losers") or raw.get("losers") or raw.get("negatively_affected") or []
    neutrals = wl.get("neutral_parties") or raw.get("neutral_parties") or []

    return {
        "status": "ready",
        "affected_groups": affected,
        "winners_losers": {
            "potential_winners": list(winners) if isinstance(winners, list) else [],
            "potential_losers": list(losers) if isinstance(losers, list) else [],
            "neutral_parties": list(neutrals) if isinstance(neutrals, list) else [],
        },
        "geographic_impact": raw.get("geographic_impact")
        or raw.get("geographic_regions")
        or None,
    }


def _normalize_policy_analysis(
    raw: Dict[str, Any], categories: Optional[list] = None
) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    breakdown = raw.get("category_breakdown")
    if not isinstance(breakdown, dict):
        breakdown = {}
    # Build breakdown from categories[] if enricher returned only that
    if not breakdown and categories:
        for cat in categories:
            if not isinstance(cat, dict):
                continue
            area = cat.get("area")
            if not area:
                continue
            impact = cat.get("impact_level", "medium")
            if isinstance(impact, (int, float)):
                score = float(impact)
            elif impact == "high":
                score = 0.9
            elif impact == "low":
                score = 0.4
            else:
                score = 0.7
            breakdown[area] = {
                "relevance_score": score,
                "reasoning": cat.get("reasoning") or "",
            }

    aspects = raw.get("controversial_aspects") or []
    if not isinstance(aspects, list):
        aspects = []

    return {
        "status": "ready",
        "overall_assessment": raw.get("overall_assessment") or raw.get("assessment"),
        "category_breakdown": breakdown,
        "controversial_aspects": aspects,
        "bipartisan_potential": raw.get("bipartisan_potential"),
    }


def run_downstream_enrichments(bill, analyzer) -> Dict[str, Any]:
    """
    Run stakeholder + policy_analysis Gemini passes and merge into a new analysis version.

    Returns the merged analysis dict (also persisted when bill supports versioning).
    """
    from services.ops_alert_service import (
        ENRICHMENT_FINISHED,
        ENRICHMENT_QUEUED,
        notify_gemini_failure,
    )

    model_name = getattr(analyzer, "model_name", None) or GEMINI_MODEL
    active = bill.get_active_ai_analysis() if hasattr(bill, "get_active_ai_analysis") else None
    base = attach_policy_areas((active.get_analysis_data() if active else {}) or {})
    stubs = pending_enrichment_stubs()
    if "policy_analysis" not in base or not isinstance(base.get("policy_analysis"), dict):
        base["policy_analysis"] = stubs["policy_analysis"]
    if "stakeholders" not in base or not isinstance(base.get("stakeholders"), dict):
        base["stakeholders"] = stubs["stakeholders"]

    # Already done?
    pa = base.get("policy_analysis") or {}
    st = base.get("stakeholders") or {}
    if pa.get("status") == "ready" and st.get("status") == "ready":
        return base

    # Need ~2 requests for both enrichers. Do not use
    # get_quota_info()["status"]["safe_remaining_requests"] — that key is not
    # under status (always defaulted to 0 and falsely skipped every poll).
    ok, remaining, reset_in = enrichment_quota_ok(analyzer)
    if not ok:
        logger.info(
            f"Enrichments deferred for {bill.get_bill_identifier()}: "
            f"remaining_requests={remaining} reset_in={reset_in:.0f}s"
        )
        # Keep pending (retry when RPM recovers). Do not persist a new
        # analysis version or flip to skipped — that caused ops spam + churn.
        try:
            notify_gemini_failure(
                ENRICHMENT_FINISHED,
                (
                    f"Enrichments deferred for {bill.get_bill_identifier()} "
                    f"(remaining_requests={remaining}, "
                    f"limit_cause=local_minute_budget, model={model_name})."
                ),
                severity="info",
                bill=bill,
                provider_model=model_name,
                source="enricher",
                extra={
                    "event": "deferred",
                    "enrichment": "both",
                    "skipped": True,
                    "limit_cause": "local_minute_budget",
                    "remaining_requests": remaining,
                    "time_until_reset": reset_in,
                    "provider_model": model_name,
                },
            )
        except Exception:
            pass
        return {
            **base,
            "enrichments_limit_cause": "local_minute_budget",
            "enrichments_deferred": True,
            "enrichments_retry_after_seconds": reset_in,
        }

    title = bill.title or "Unknown Bill"
    text = ""
    if hasattr(bill, "full_text") and bill.full_text:
        text = bill.full_text
    elif hasattr(bill, "get_full_text"):
        text = bill.get_full_text() or ""
    # Cap prompt size for enrichers (full text can be large)
    text_sample = text[:80000] if text else (bill.summary or "")

    categories = []
    pi = base.get("policy_implications") or {}
    if isinstance(pi, dict) and isinstance(pi.get("categories"), list):
        categories = pi["categories"]

    try:
        notify_gemini_failure(
            ENRICHMENT_QUEUED,
            (
                f"Enrichments queued for {bill.get_bill_identifier()} "
                f"(stakeholders + policy_analysis, model={model_name})."
            ),
            severity="info",
            bill=bill,
            provider_model=model_name,
            source="enricher",
            extra={
                "event": "queued",
                "enrichment": "both",
                "provider_model": model_name,
            },
        )
    except Exception:
        pass

    # --- Stakeholders ---
    stake_prompt = f"""Analyze stakeholders affected by this congressional bill.

Bill Title: {title}

Bill Text:
{text_sample}

Return JSON exactly in this shape:
{{
  "affected_groups": [
    {{
      "group": "name of group",
      "impact_type": "positive|negative|neutral",
      "impact_description": "how they are affected"
    }}
  ],
  "winners_losers": {{
    "potential_winners": ["..."],
    "potential_losers": ["..."],
    "neutral_parties": ["..."]
  }},
  "geographic_impact": "brief geographic impact summary or null"
}}
"""
    stake_raw = analyzer._call_ai_json(stake_prompt) or {}
    base["stakeholders"] = _normalize_stakeholders(stake_raw)

    # --- Policy analysis (deep) ---
    cats_blob = ""
    if categories:
        import json

        cats_blob = json.dumps(categories, indent=2)[:4000]

    policy_prompt = f"""Provide a deeper policy analysis for this congressional bill.

Bill Title: {title}

Known category labels (use these areas in category_breakdown):
{cats_blob or "Infer from the bill text."}

Bill Text:
{text_sample}

Return JSON exactly in this shape:
{{
  "overall_assessment": "2-4 sentence policy assessment",
  "category_breakdown": {{
    "Category Name": {{
      "relevance_score": 0.0,
      "reasoning": "why this area matters for the bill"
    }}
  }},
  "controversial_aspects": ["..."],
  "bipartisan_potential": "low|medium|high or a short phrase"
}}
relevance_score must be a float from 0.0 to 1.0.
"""
    policy_raw = analyzer._call_ai_json(policy_prompt) or {}
    base["policy_analysis"] = _normalize_policy_analysis(policy_raw, categories)

    base["provider_model"] = model_name
    base["enrichments_completed"] = True
    base.pop("enrichments_limit_cause", None)

    _persist_merged(bill, base, analyzer)

    try:
        notify_gemini_failure(
            ENRICHMENT_FINISHED,
            (
                f"Enrichments finished for {bill.get_bill_identifier()} "
                f"(model={model_name})."
            ),
            severity="info",
            bill=bill,
            provider_model=model_name,
            source="enricher",
            extra={
                "event": "finished",
                "enrichment": "both",
                "stakeholders_status": base["stakeholders"].get("status"),
                "policy_analysis_status": base["policy_analysis"].get("status"),
                "provider_model": model_name,
            },
        )
    except Exception:
        pass

    return base


def _persist_merged(bill, analysis_data: Dict[str, Any], analyzer) -> None:
    if not hasattr(bill, "create_new_analysis_version"):
        if hasattr(bill, "set_ai_analysis"):
            bill.set_ai_analysis(analysis_data)
        return

    complexity_assessment = analysis_data.get("complexity_assessment") or {}
    complexity_score = None
    if isinstance(complexity_assessment, dict):
        complexity_score = complexity_assessment.get("complexity_score")
    controversy = analysis_data.get("controversy_score", 0.0)
    if not isinstance(controversy, (int, float)):
        controversy = 0.0

    bill.create_new_analysis_version(
        analysis_data=analysis_data,
        complexity_score=complexity_score,
        controversy_score=controversy,
        analysis_method=analysis_data.get("analysis_method") or "enriched",
        chunks_analyzed=analysis_data.get("chunks_analyzed"),
        processing_time=None,
        provider_model=getattr(analyzer, "model_name", None) or GEMINI_MODEL,
    )
    # display_ready should already be true; refresh in case categories exist
    if hasattr(bill, "update_display_ready_status"):
        bill.update_display_ready_status()
