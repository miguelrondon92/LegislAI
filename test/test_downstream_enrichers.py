"""QA for downstream stakeholder + policy enrichers."""
import unittest
from unittest.mock import MagicMock, patch

from services.analysis_enrichers import (
    attach_policy_areas,
    enrichments_need_work,
    pending_enrichment_stubs,
    run_downstream_enrichments,
    _normalize_policy_analysis,
    _normalize_stakeholders,
)


class TestCanonicalShapes(unittest.TestCase):
    def test_pending_stubs(self):
        stubs = pending_enrichment_stubs()
        self.assertEqual(stubs["policy_analysis"]["status"], "pending")
        self.assertEqual(stubs["stakeholders"]["status"], "pending")
        self.assertIn("affected_groups", stubs["stakeholders"])
        self.assertIn("winners_losers", stubs["stakeholders"])

    def test_attach_policy_areas(self):
        data = attach_policy_areas(
            {
                "policy_implications": {
                    "primary_category": "Healthcare",
                    "secondary_categories": ["Finance"],
                    "categories": [{"area": "Healthcare", "impact_level": "high"}],
                }
            }
        )
        self.assertEqual(data["policy_areas"]["primary_category"], "Healthcare")
        self.assertEqual(data["policy_areas"]["secondary_categories"], ["Finance"])
        # Mapping categories preserved
        self.assertEqual(len(data["policy_implications"]["categories"]), 1)

    def test_normalize_stakeholders_from_legacy_flat(self):
        raw = {
            "winners": ["Hospitals"],
            "losers": ["Insurers"],
            "neutral_parties": ["States"],
            "key_interest_groups": ["AMA"],
        }
        out = _normalize_stakeholders(raw)
        self.assertEqual(out["status"], "ready")
        self.assertTrue(out["affected_groups"])
        self.assertIn("Hospitals", out["winners_losers"]["potential_winners"])
        self.assertIn("Insurers", out["winners_losers"]["potential_losers"])

    def test_normalize_stakeholders_template_shape(self):
        raw = {
            "affected_groups": [
                {
                    "group": "Farmers",
                    "impact_type": "positive",
                    "impact_description": "subsidies",
                }
            ],
            "winners_losers": {
                "potential_winners": ["Farmers"],
                "potential_losers": [],
                "neutral_parties": [],
            },
            "geographic_impact": "Midwest",
        }
        out = _normalize_stakeholders(raw)
        self.assertEqual(out["affected_groups"][0]["group"], "Farmers")
        self.assertEqual(out["geographic_impact"], "Midwest")

    def test_normalize_policy_from_categories(self):
        out = _normalize_policy_analysis(
            {"overall_assessment": "Significant reform."},
            categories=[
                {"area": "Tax", "impact_level": "high", "reasoning": "rates change"}
            ],
        )
        self.assertEqual(out["status"], "ready")
        self.assertIn("Tax", out["category_breakdown"])
        self.assertAlmostEqual(out["category_breakdown"]["Tax"]["relevance_score"], 0.9)


class TestEnrichmentsNeedWork(unittest.TestCase):
    def test_pending_needs_work(self):
        data = attach_policy_areas({"summary": "x", **pending_enrichment_stubs()})
        self.assertTrue(enrichments_need_work(data))

    def test_ready_does_not(self):
        data = {
            "policy_analysis": {"status": "ready"},
            "stakeholders": {"status": "ready"},
        }
        self.assertFalse(enrichments_need_work(data))

    def test_skipped_retries(self):
        data = {
            "policy_analysis": {"status": "skipped"},
            "stakeholders": {"status": "skipped"},
        }
        self.assertTrue(enrichments_need_work(data))


class TestRunDownstreamEnrichments(unittest.TestCase):
    def _bill(self, analysis_data):
        bill = MagicMock()
        bill.title = "Test Bill"
        bill.summary = "A short summary."
        bill.full_text = "Section 1. Short title. This Act may be cited as Test."
        bill.get_bill_identifier.return_value = "119-HR999"
        active = MagicMock()
        active.get_analysis_data.return_value = analysis_data
        bill.get_active_ai_analysis.return_value = active
        bill.create_new_analysis_version = MagicMock()
        bill.update_display_ready_status = MagicMock()
        return bill

    def _analyzer(self, remaining=10):
        analyzer = MagicMock()
        analyzer.model_name = "gemini-3.5-flash-lite"
        analyzer.get_rate_limit_status.return_value = {
            "remaining_requests": remaining,
            "time_until_reset": 30.0,
        }
        analyzer.get_quota_info.return_value = {
            "current_usage": {
                "remaining_requests": remaining,
                "safe_remaining_requests": max(0, remaining - 2),
            },
            "status": {"can_handle_small_bill": remaining >= 2},
            "timing": {"time_until_reset": 30.0},
        }
        return analyzer

    @patch("services.ops_alert_service.notify_gemini_failure", MagicMock())
    def test_defer_when_quota_low_without_persist(self):
        base = {
            "summary": "core summary",
            "policy_implications": {
                "primary_category": "Tax",
                "secondary_categories": [],
                "categories": [{"area": "Tax", "impact_level": "high"}],
            },
            **pending_enrichment_stubs(),
        }
        bill = self._bill(base)
        analyzer = self._analyzer(remaining=0)

        out = run_downstream_enrichments(bill, analyzer)

        self.assertTrue(out.get("enrichments_deferred"))
        self.assertEqual(out["enrichments_limit_cause"], "local_minute_budget")
        # Stay pending — do not churn versions or flip to skipped
        self.assertEqual(out["stakeholders"]["status"], "pending")
        self.assertEqual(out["policy_analysis"]["status"], "pending")
        bill.create_new_analysis_version.assert_not_called()

    def test_quota_helper_reads_rate_limit_status(self):
        from services.analysis_enrichers import enrichment_quota_ok

        analyzer = MagicMock()
        analyzer.get_rate_limit_status.return_value = {
            "remaining_requests": 10,
            "time_until_reset": 12.0,
        }
        ok, remaining, reset = enrichment_quota_ok(analyzer)
        self.assertTrue(ok)
        self.assertEqual(remaining, 10)
        self.assertEqual(reset, 12.0)

    def test_quota_helper_does_not_use_empty_status_nest(self):
        """Regression: get_quota_info()['status'] has no safe_remaining_requests."""
        from services.analysis_enrichers import enrichment_quota_ok

        analyzer = MagicMock(spec=["get_quota_info"])
        analyzer.get_quota_info.return_value = {
            "current_usage": {"remaining_requests": 8, "safe_remaining_requests": 6},
            "timing": {"time_until_reset": 5},
            "status": {"can_handle_small_bill": True},
        }
        ok, remaining, _ = enrichment_quota_ok(analyzer)
        self.assertTrue(ok)
        self.assertEqual(remaining, 8)

    def test_merge_ready_shape(self):
        base = attach_policy_areas(
            {
                "summary": "core",
                "policy_implications": {
                    "primary_category": "Healthcare",
                    "secondary_categories": ["Finance"],
                    "categories": [
                        {
                            "area": "Healthcare",
                            "impact_level": "high",
                            "reasoning": "coverage",
                        }
                    ],
                },
                **pending_enrichment_stubs(),
                "analysis_method": "single_pass_full_text",
            }
        )
        bill = self._bill(base)
        analyzer = self._analyzer(remaining=5)

        def fake_json(prompt):
            if "stakeholders" in prompt.lower() or "Affected" in prompt or "winners_losers" in prompt:
                return {
                    "affected_groups": [
                        {
                            "group": "Patients",
                            "impact_type": "positive",
                            "impact_description": "more coverage",
                        }
                    ],
                    "winners_losers": {
                        "potential_winners": ["Patients"],
                        "potential_losers": ["Insurers"],
                        "neutral_parties": [],
                    },
                    "geographic_impact": "Nationwide",
                }
            return {
                "overall_assessment": "Expands access.",
                "category_breakdown": {
                    "Healthcare": {"relevance_score": 0.95, "reasoning": "core topic"}
                },
                "controversial_aspects": ["cost"],
                "bipartisan_potential": "medium",
            }

        analyzer._call_ai_json.side_effect = fake_json

        with patch("services.ops_alert_service.notify_gemini_failure", MagicMock()):
            out = run_downstream_enrichments(bill, analyzer)

        self.assertEqual(out["stakeholders"]["status"], "ready")
        self.assertEqual(out["policy_analysis"]["status"], "ready")
        self.assertEqual(out["stakeholders"]["affected_groups"][0]["group"], "Patients")
        self.assertIn("Patients", out["stakeholders"]["winners_losers"]["potential_winners"])
        self.assertEqual(out["policy_analysis"]["overall_assessment"], "Expands access.")
        self.assertTrue(out.get("enrichments_completed"))
        # Core summary / policy_areas preserved
        self.assertEqual(out["summary"], "core")
        self.assertEqual(out["policy_areas"]["primary_category"], "Healthcare")
        bill.create_new_analysis_version.assert_called()


class TestCoreIndependentOfEnrichments(unittest.TestCase):
    """Core Tier A success does not require stakeholders; display_ready independent."""

    def test_core_success_without_stakeholder_content(self):
        # Smoke: pending stubs attach without stakeholders content
        results = {
            "summary": {"overview": "ok"},
            "policy_implications": {
                "primary_category": "Tax",
                "secondary_categories": [],
                "categories": [{"area": "Tax", "impact_level": "high"}],
            },
        }
        results.update(pending_enrichment_stubs())
        results = attach_policy_areas(results)
        self.assertEqual(results["stakeholders"]["status"], "pending")
        self.assertFalse(results["stakeholders"]["affected_groups"])
        self.assertEqual(results["policy_analysis"]["status"], "pending")
        # Categories for mappings still present (display_ready inputs)
        self.assertTrue(results["policy_implications"]["categories"])
        self.assertEqual(results["policy_areas"]["primary_category"], "Tax")
        # Enrichments incomplete does not erase core summary
        self.assertEqual(results["summary"]["overview"], "ok")
        self.assertTrue(enrichments_need_work(results))


if __name__ == "__main__":
    unittest.main()
