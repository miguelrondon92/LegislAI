"""QA for size-aware analysis: Tier A/B routing, resume, chunker, in-flight dedupe."""
import unittest
from unittest.mock import MagicMock, patch

from utils.bill_chunker import BillChunker, BillChunk


class TestBillChunkerNoOverlap(unittest.TestCase):
    def test_sections_non_overlapping(self):
        text = (
            "SEC. 1. Short title.\nThis Act may be cited as the Test Act.\n\n"
            "SEC. 2. Findings.\nCongress finds that testing is useful.\n\n"
            "SEC. 3. Definitions.\nIn this Act, the term foo means bar.\n"
        )
        chunker = BillChunker()
        sections = chunker._extract_sections(text)
        self.assertGreaterEqual(len(sections), 2)
        for i, a in enumerate(sections):
            for b in sections[i + 1 :]:
                overlaps = a.start_position < b.end_position and b.start_position < a.end_position
                self.assertFalse(overlaps, f"overlap {a.section_number} / {b.section_number}")

    def test_macro_chunks_document_order_and_keys(self):
        # Build enough section text to force multiple macros
        parts = []
        for i in range(1, 21):
            parts.append(f"SEC. {i}. Section {i}.\n" + ("word " * 200) + "\n")
        text = "\n".join(parts)
        chunker = BillChunker()
        macros = chunker.build_macro_chunks(text, max_chars=3000)
        self.assertGreaterEqual(len(macros), 2)
        keys = [m.ensure_key() for m in macros]
        self.assertEqual(len(keys), len(set(keys)))
        # Document order: starts non-decreasing
        starts = [m.start_position for m in macros]
        self.assertEqual(starts, sorted(starts))

    def test_filter_unanalyzed(self):
        chunker = BillChunker()
        c1 = BillChunk(content="aaa", chunk_type="macro", start_position=0, end_position=3)
        c2 = BillChunk(content="bbb", chunk_type="macro", start_position=3, end_position=6)
        c1.ensure_key()
        c2.ensure_key()
        remaining = chunker.filter_unanalyzed([c1, c2], {c1.chunk_key})
        self.assertEqual(len(remaining), 1)
        self.assertEqual(remaining[0].chunk_key, c2.chunk_key)

    def test_no_front_of_bill_importance_bias(self):
        chunker = BillChunker()
        early = chunker._calculate_section_importance("1", "short")
        late = chunker._calculate_section_importance("99", "short")
        self.assertEqual(early, late)


class TestTierRouting(unittest.TestCase):
    def _make_analyzer(self):
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer

        analyzer = EnhancedAIAnalyzer.__new__(EnhancedAIAnalyzer)
        analyzer.model_name = "gemini-3.5-flash-lite"
        analyzer.client = MagicMock()
        analyzer.api_key = "test"
        analyzer.max_requests_per_minute = 15
        analyzer.max_input_tokens_per_minute = 250_000
        analyzer.usable_tpm_headroom = 220_000
        analyzer.max_tokens_per_request = 200_000
        analyzer.tier_a_max_tokens = 150_000
        analyzer.macro_chunk_target_tokens = 120_000
        analyzer.estimated_tokens_per_char = 0.30
        analyzer.max_budget_waits_per_analysis = 2
        analyzer.max_chunks_per_bill = 50
        analyzer.max_retries = 0
        analyzer.base_delay = 0.1
        analyzer.max_delay = 1.0
        analyzer.backoff_multiplier = 2.0
        analyzer.jitter_factor = 0.0
        analyzer.request_count = 0
        analyzer.last_request_time = None
        analyzer.requests_this_minute = 0
        analyzer.tokens_this_minute = 0
        analyzer.minute_start_time = None
        analyzer._hit_gemini_api_429 = False
        analyzer.bill_chunker = BillChunker()
        analyzer.policy_categories = ["Taxation", "Health Care", "Government Operations"]
        analyzer.suspicious_patterns = []
        return analyzer

    def test_tier_a_uses_two_json_calls_and_is_complete(self):
        analyzer = self._make_analyzer()
        core = {
            "summary": {
                "main_summary": "A short bill.",
                "key_provisions": ["x"],
                "funding_amounts": "Unknown",
                "implementation_timeline": "Unknown",
                "plain_language_explanation": "A short bill.",
            },
            "policy_implications": {
                "primary_category": "Taxation",
                "secondary_categories": [],
                "categories": [{"area": "Taxation", "impact_level": "low", "reasoning": "t"}],
                "primary_policy_area": "Taxation",
            },
            "stakeholders": {"winners": [], "losers": []},
            "complexity_assessment": {"complexity_score": 0.2},
            "controversy_score": 0.1,
        }
        integrity = {
            "hidden_provisions": {
                "detected_provisions": [],
                "overall_hidden_risk_score": 0.0,
            }
        }
        with patch.object(analyzer, "_call_ai_json", side_effect=[core, integrity]) as mock_json:
            text = "Title: Test\n\nSEC. 1. Short title.\nThis Act is short. " * 20
            result = analyzer._analyze_tier_a(text, "Test Act", "summary", len(text))
        self.assertEqual(mock_json.call_count, 2)
        self.assertEqual(result["analysis_method"], "single_pass_full_text")
        self.assertEqual(result["analysis_tier"], "A")
        self.assertFalse(result["is_partial"])
        self.assertEqual(result["completion_percentage"], 100.0)
        self.assertEqual(result["chars_analyzed"], len(text))

    def test_analyze_bill_routes_small_text_to_tier_a(self):
        analyzer = self._make_analyzer()
        with patch.object(
            analyzer,
            "_analyze_tier_a",
            return_value={
                "analysis_method": "single_pass_full_text",
                "analysis_tier": "A",
                "is_partial": False,
                "completion_percentage": 100.0,
                "summary": {"main_summary": "ok"},
            },
        ) as tier_a, patch.object(analyzer, "_analyze_tier_b") as tier_b, patch.object(
            analyzer, "_persist_analysis_results"
        ), patch.object(analyzer, "_calculate_overall_risk_score", return_value=0.1):
            out = analyzer.analyze_bill("Short bill text for testing.", title="T")
        tier_a.assert_called_once()
        tier_b.assert_not_called()
        self.assertEqual(out["analysis_tier"], "A")

    def test_tier_b_resume_increases_coverage(self):
        analyzer = self._make_analyzer()
        # Force tiny macros so we get many chunks
        analyzer.macro_chunk_target_tokens = 50  # ~166 chars
        parts = []
        for i in range(1, 12):
            parts.append(f"SEC. {i}. Section {i}.\n" + ("legislation text " * 40) + "\n")
        text = "\n".join(parts)
        total_chars = len(text)

        map_payload = {
            "summary": "portion",
            "key_provisions": ["p"],
            "hidden_provisions": [],
        }

        # First wave: no prior
        with patch.object(analyzer, "_map_macro_chunk", return_value=map_payload), patch.object(
            analyzer, "_select_tier_b_wave", side_effect=lambda rem, allow_budget_waits=True: rem[:2]
        ), patch.object(analyzer, "_reduce_tier_b", return_value={"summary": {"main_summary": "full"}}):
            wave1 = analyzer._analyze_tier_b(
                text, "Big Act", "", total_chars, prior_analysis=None, allow_budget_waits=False
            )

        self.assertTrue(wave1["is_partial"])
        self.assertGreater(wave1["completion_percentage"], 0)
        keys1 = set(wave1["analyzed_chunk_keys"])
        self.assertEqual(len(keys1), 2)

        # Second wave: resume
        with patch.object(analyzer, "_map_macro_chunk", return_value=map_payload), patch.object(
            analyzer, "_select_tier_b_wave", side_effect=lambda rem, allow_budget_waits=True: rem[:2]
        ), patch.object(analyzer, "_reduce_tier_b", return_value={"summary": {"main_summary": "full"}}):
            wave2 = analyzer._analyze_tier_b(
                text,
                "Big Act",
                "",
                total_chars,
                prior_analysis=wave1,
                allow_budget_waits=False,
            )

        keys2 = set(wave2["analyzed_chunk_keys"])
        self.assertTrue(keys1.issubset(keys2))
        self.assertGreater(len(keys2), len(keys1))
        self.assertGreaterEqual(
            wave2["completion_percentage"], wave1["completion_percentage"]
        )


class TestInFlightDedupe(unittest.TestCase):
    def test_second_acquire_fails(self):
        import routes as routes_mod

        # Isolate process lock for test
        with routes_mod._analyzing_lock:
            routes_mod._analyzing_bill_ids.clear()

        self.assertTrue(routes_mod._try_acquire_analysis_slot(999001))
        self.assertFalse(routes_mod._try_acquire_analysis_slot(999001))
        routes_mod._release_analysis_slot(999001)
        self.assertTrue(routes_mod._try_acquire_analysis_slot(999001))
        routes_mod._release_analysis_slot(999001)

    def test_is_tier_b_partial(self):
        import routes as routes_mod

        self.assertTrue(
            routes_mod._is_tier_b_partial(
                {"is_partial": True, "analysis_method": "map_reduce_macro_chunks"}
            )
        )
        self.assertFalse(
            routes_mod._is_tier_b_partial(
                {"is_partial": True, "analysis_method": "single_pass_full_text"}
            )
        )
        self.assertFalse(routes_mod._is_tier_b_partial({"is_partial": False}))
        # Legacy chunked partials are not Tier B — clear + re-ingest instead of hardcoding
        self.assertFalse(
            routes_mod._is_tier_b_partial(
                {
                    "is_partial": True,
                    "analysis_method": "enhanced_chunked_with_hidden_detection",
                    "completion_percentage": 40.0,
                }
            )
        )


class TestGovernorTPM(unittest.TestCase):
    def test_record_request_tracks_tokens(self):
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer

        analyzer = EnhancedAIAnalyzer.__new__(EnhancedAIAnalyzer)
        analyzer.max_requests_per_minute = 15
        analyzer.usable_tpm_headroom = 1000
        analyzer.requests_this_minute = 0
        analyzer.tokens_this_minute = 0
        analyzer.minute_start_time = None
        analyzer.request_count = 0
        analyzer.last_request_time = None

        self.assertTrue(analyzer._record_request(400))
        self.assertEqual(analyzer.tokens_this_minute, 400)
        self.assertTrue(analyzer._record_request(400))
        self.assertFalse(analyzer._record_request(400))  # would exceed 1000


if __name__ == "__main__":
    unittest.main()
