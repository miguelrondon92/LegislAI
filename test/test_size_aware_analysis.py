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
        from services.gemini_rate_budget import GeminiRateBudget

        analyzer = EnhancedAIAnalyzer.__new__(EnhancedAIAnalyzer)
        analyzer._budget = GeminiRateBudget(persist_to_db=False)
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

    def test_empty_wave_preserves_map_findings(self):
        analyzer = self._make_analyzer()
        analyzer.macro_chunk_target_tokens = 50
        parts = []
        for i in range(1, 8):
            parts.append(f"SEC. {i}. Section {i}.\n" + ("legislation text " * 40) + "\n")
        text = "\n".join(parts)
        total_chars = len(text)

        prior = {
            "analysis_method": "map_reduce_macro_chunks",
            "analysis_tier": "B",
            "is_partial": True,
            "analyzed_chunk_keys": ["k1", "k2"],
            "tier_b_map_findings": [
                {"chunk_key": "k1", "summary": "first"},
                {"chunk_key": "k2", "summary": "second"},
            ],
            "summary": {"main_summary": "kept summary", "key_provisions": ["a"]},
            "completion_percentage": 40.0,
        }

        with patch.object(analyzer, "_select_tier_b_wave", return_value=[]):
            out = analyzer._analyze_tier_b(
                text,
                "Big Act",
                "",
                total_chars,
                prior_analysis=prior,
                allow_budget_waits=False,
            )

        self.assertTrue(out.get("_no_progress"))
        self.assertEqual(len(out.get("tier_b_map_findings") or []), 2)
        self.assertEqual(out["summary"]["main_summary"], "kept summary")
        self.assertEqual(out["analysis_method"], "map_reduce_macro_chunks")
        self.assertTrue(out["is_partial"])

    def test_orphan_keys_are_remapped(self):
        analyzer = self._make_analyzer()
        analyzer.macro_chunk_target_tokens = 50
        parts = []
        for i in range(1, 6):
            parts.append(f"SEC. {i}. Section {i}.\n" + ("legislation text " * 40) + "\n")
        text = "\n".join(parts)
        total_chars = len(text)
        macros = analyzer.bill_chunker.build_macro_chunks(
            text, max_chars=analyzer._macro_chunk_max_chars()
        )
        self.assertGreaterEqual(len(macros), 2)
        k0 = macros[0].ensure_key()
        k1 = macros[1].ensure_key()
        prior = {
            "analyzed_chunk_keys": [k0, k1],
            # Missing finding for k1 — should remap k1
            "tier_b_map_findings": [{"chunk_key": k0, "summary": "ok"}],
        }
        mapped = []

        def fake_map(chunk, title, index):
            mapped.append(chunk.ensure_key())
            return {"chunk_key": chunk.ensure_key(), "summary": "remapped"}

        with patch.object(analyzer, "_map_macro_chunk", side_effect=fake_map), patch.object(
            analyzer,
            "_select_tier_b_wave",
            side_effect=lambda rem, allow_budget_waits=True: rem[:1],
        ), patch.object(
            analyzer, "_reduce_tier_b", return_value={"summary": {"main_summary": "full"}}
        ):
            out = analyzer._analyze_tier_b(
                text,
                "Big Act",
                "",
                total_chars,
                prior_analysis=prior,
                allow_budget_waits=False,
            )

        self.assertIn(k1, mapped)
        out_keys = {m.get("chunk_key") for m in (out.get("tier_b_map_findings") or [])}
        self.assertIn(k0, out_keys)
        self.assertIn(k1, out_keys)

    def test_failed_map_not_in_analyzed_chunk_keys(self):
        """map_failed stubs must not count as done (failed ≠ done)."""
        analyzer = self._make_analyzer()
        analyzer.macro_chunk_target_tokens = 50
        parts = []
        for i in range(1, 6):
            parts.append(f"SEC. {i}. Section {i}.\n" + ("legislation text " * 40) + "\n")
        text = "\n".join(parts)
        total_chars = len(text)

        def fail_map(chunk, title, index):
            return {
                "chunk_key": chunk.ensure_key(),
                "summary": "",
                "key_provisions": [],
                "map_failed": True,
            }

        with patch.object(analyzer, "_map_macro_chunk", side_effect=fail_map), patch.object(
            analyzer,
            "_select_tier_b_wave",
            side_effect=lambda rem, allow_budget_waits=True: rem[:2],
        ), patch.object(
            analyzer, "_reduce_tier_b", return_value={"summary": {"main_summary": "should not run"}}
        ):
            out = analyzer._analyze_tier_b(
                text, "Big Act", "", total_chars, prior_analysis=None, allow_budget_waits=False
            )

        self.assertTrue(out["is_partial"])
        self.assertLess(out["completion_percentage"], 100.0)
        self.assertEqual(out.get("analyzed_chunk_keys") or [], [])
        self.assertEqual(out.get("tier_b_map_findings") or [], [])
        self.assertIn(out.get("limit_cause"), ("map_failures", "gemini_api_429", "local_minute_budget"))

    def test_map_failed_prior_is_remapped(self):
        """Prior map_failed keys are remapped on the next wave."""
        analyzer = self._make_analyzer()
        analyzer.macro_chunk_target_tokens = 50
        parts = []
        for i in range(1, 6):
            parts.append(f"SEC. {i}. Section {i}.\n" + ("legislation text " * 40) + "\n")
        text = "\n".join(parts)
        total_chars = len(text)
        macros = analyzer.bill_chunker.build_macro_chunks(
            text, max_chars=analyzer._macro_chunk_max_chars()
        )
        self.assertGreaterEqual(len(macros), 2)
        k0 = macros[0].ensure_key()
        k1 = macros[1].ensure_key()
        prior = {
            "analyzed_chunk_keys": [k0, k1],
            "tier_b_map_findings": [
                {
                    "chunk_key": k0,
                    "summary": "",
                    "map_failed": True,
                },
                {
                    "chunk_key": k1,
                    "summary": "",
                    "map_failed": True,
                },
            ],
            "is_partial": False,
            "completion_percentage": 100.0,
        }
        mapped = []

        def fake_map(chunk, title, index):
            mapped.append(chunk.ensure_key())
            return {"chunk_key": chunk.ensure_key(), "summary": "recovered", "key_provisions": ["p"]}

        with patch.object(analyzer, "_map_macro_chunk", side_effect=fake_map), patch.object(
            analyzer,
            "_select_tier_b_wave",
            side_effect=lambda rem, allow_budget_waits=True: rem[:2],
        ), patch.object(
            analyzer, "_reduce_tier_b", return_value={"summary": {"main_summary": "ok"}}
        ):
            out = analyzer._analyze_tier_b(
                text,
                "Big Act",
                "",
                total_chars,
                prior_analysis=prior,
                allow_budget_waits=False,
            )

        self.assertIn(k0, mapped)
        self.assertIn(k1, mapped)
        usable = out.get("tier_b_map_findings") or []
        self.assertTrue(all(not m.get("map_failed") for m in usable))
        self.assertIn(k0, out.get("analyzed_chunk_keys") or [])

    def test_all_failed_maps_refuse_complete(self):
        """All-failed maps stay partial — never fake 100% / garbage reduce."""
        analyzer = self._make_analyzer()
        analyzer.macro_chunk_target_tokens = 50
        parts = []
        for i in range(1, 5):
            parts.append(f"SEC. {i}. Section {i}.\n" + ("legislation text " * 40) + "\n")
        text = "\n".join(parts)
        total_chars = len(text)
        macros = analyzer.bill_chunker.build_macro_chunks(
            text, max_chars=analyzer._macro_chunk_max_chars()
        )
        keys = [m.ensure_key() for m in macros]
        prior = {
            "analyzed_chunk_keys": keys,
            "tier_b_map_findings": [
                {"chunk_key": k, "summary": "", "map_failed": True} for k in keys
            ],
            "is_partial": False,
            "completion_percentage": 100.0,
        }

        # No remaining keys after stripping map_failed — must refuse complete
        with patch.object(analyzer, "_select_tier_b_wave", return_value=[]), patch.object(
            analyzer,
            "_reduce_tier_b",
            return_value={
                "summary": {
                    "main_summary": "mapping errors across all provided chunks",
                }
            },
        ) as reduce_mock:
            # Remap path: remaining macros after clearing failed keys
            with patch.object(
                analyzer,
                "_map_macro_chunk",
                return_value={"summary": "", "map_failed": True},
            ):
                # Force remaining by using prior that will strip all keys
                out = analyzer._analyze_tier_b(
                    text,
                    "Big Act",
                    "",
                    total_chars,
                    prior_analysis=prior,
                    allow_budget_waits=False,
                )

        self.assertTrue(out["is_partial"])
        self.assertLess(out.get("completion_percentage", 0), 100.0)
        self.assertNotEqual(out.get("analysis_completeness"), "full")
        # Reduce must not produce a shipped complete from empty usable maps
        if reduce_mock.called:
            self.assertTrue(out["is_partial"])

    def test_tier_b_needs_resume_fake_complete(self):
        import routes as routes_mod

        fake = {
            "is_partial": False,
            "analysis_method": "map_reduce_macro_chunks",
            "analysis_tier": "B",
            "completion_percentage": 100.0,
            "total_chunks_available": 6,
            "tier_b_map_findings": [
                {"chunk_key": f"k{i}", "summary": "", "map_failed": True}
                for i in range(6)
            ],
            "summary": {
                "main_summary": "mapping errors across all provided chunks",
            },
        }
        self.assertTrue(routes_mod._tier_b_needs_resume(fake))
        self.assertFalse(
            routes_mod._tier_b_needs_resume(
                {
                    "is_partial": False,
                    "analysis_method": "map_reduce_macro_chunks",
                    "tier_b_map_findings": [
                        {"chunk_key": "k0", "summary": "real content", "key_provisions": ["a"]}
                    ],
                    "total_chunks_available": 1,
                    "summary": {"main_summary": "A defense authorization bill."},
                }
            )
        )


class TestInFlightDedupe(unittest.TestCase):
    def test_second_acquire_fails(self):
        import routes as routes_mod
        from unittest.mock import patch

        with patch(
            "routes.bill_work_lease.try_acquire", side_effect=[True, False, True]
        ) as acq, patch("routes.bill_work_lease.release") as rel:
            self.assertTrue(routes_mod._try_acquire_analysis_slot(999001))
            self.assertFalse(routes_mod._try_acquire_analysis_slot(999001))
            routes_mod._release_analysis_slot(999001)
            self.assertTrue(routes_mod._try_acquire_analysis_slot(999001))
            routes_mod._release_analysis_slot(999001)
            self.assertEqual(acq.call_count, 3)
            self.assertEqual(rel.call_count, 2)

    def test_in_flight_skip_does_not_persist_ops_alert(self):
        """Refresh while analysis runs must not spam OpsAlert with in_flight skips."""
        import routes as routes_mod
        from unittest.mock import MagicMock, patch

        bill = MagicMock()
        bill.id = 8800
        bill.get_bill_identifier.return_value = "119-HR8800"

        with patch(
            "routes.bill_work_lease.try_acquire", return_value=False
        ), patch("services.ops_alert_service.notify_gemini_failure") as notify:
            routes_mod._perform_analysis_async(bill, force_continue=True)
            notify.assert_not_called()

    def test_analysis_is_in_flight_helper(self):
        import routes as routes_mod
        from unittest.mock import patch

        with patch("routes.bill_work_lease.is_held", return_value=False):
            self.assertFalse(routes_mod._analysis_is_in_flight(42))
        with patch("routes.bill_work_lease.is_held", return_value=True):
            self.assertTrue(routes_mod._analysis_is_in_flight(42))

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

    def test_can_continue_tier_b_wave_respects_tpm(self):
        import routes as routes_mod

        class FakeAnalyzer:
            macro_chunk_target_tokens = 120_000

            def get_rate_limit_status(self):
                return {
                    "is_at_limit": False,
                    "remaining_tokens": 1000,  # too small for a macro
                    "remaining_requests": 10,
                }

        old = routes_mod.ai_analyzer
        routes_mod.ai_analyzer = FakeAnalyzer()
        try:
            self.assertFalse(routes_mod._can_continue_tier_b_wave())
        finally:
            routes_mod.ai_analyzer = old

        class OkAnalyzer:
            macro_chunk_target_tokens = 120_000

            def get_rate_limit_status(self):
                return {
                    "is_at_limit": False,
                    "remaining_tokens": 200_000,
                    "remaining_requests": 10,
                }

        routes_mod.ai_analyzer = OkAnalyzer()
        try:
            self.assertTrue(routes_mod._can_continue_tier_b_wave())
        finally:
            routes_mod.ai_analyzer = old


class TestGovernorTPM(unittest.TestCase):
    def test_record_request_tracks_tokens(self):
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer
        from services.gemini_rate_budget import GeminiRateBudget

        analyzer = EnhancedAIAnalyzer.__new__(EnhancedAIAnalyzer)
        analyzer._budget = GeminiRateBudget(
            max_requests_per_minute=15,
            usable_tpm_headroom=1000,
            persist_to_db=False,
        )
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
