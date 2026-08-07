"""Tests for shared enrichment queue (routes / RSS / backfill)."""
import unittest
from unittest.mock import MagicMock, patch

from services.analysis_enrichers import pending_enrichment_stubs
from services import enrichment_queue as eq


class TestEnrichmentDefer(unittest.TestCase):
    def setUp(self):
        with eq._enrichment_defer_lock:
            eq._enrichment_defer_until.clear()

    def tearDown(self):
        with eq._enrichment_defer_lock:
            eq._enrichment_defer_until.clear()

    def test_mark_and_is_deferred(self):
        self.assertFalse(eq.enrichment_is_deferred(42))
        eq.mark_enrichment_deferred(42, 60.0)
        self.assertTrue(eq.enrichment_is_deferred(42))

    def test_expired_defer_clears(self):
        eq.mark_enrichment_deferred(7, 60.0)
        with eq._enrichment_defer_lock:
            eq._enrichment_defer_until[7] = 0.0  # already expired
        self.assertFalse(eq.enrichment_is_deferred(7))


class TestQueueDownstreamEnrichments(unittest.TestCase):
    def setUp(self):
        with eq._enrichment_defer_lock:
            eq._enrichment_defer_until.clear()

    def tearDown(self):
        with eq._enrichment_defer_lock:
            eq._enrichment_defer_until.clear()

    def _bill(self, bill_id=101):
        bill = MagicMock()
        bill.id = bill_id
        bill.get_bill_identifier.return_value = "119-HR101"
        return bill

    def _analyzer(self, remaining=10):
        analyzer = MagicMock()
        analyzer.get_rate_limit_status.return_value = {
            "remaining_requests": remaining,
            "time_until_reset": 45.0,
        }
        return analyzer

    def test_skips_when_deferred(self):
        bill = self._bill()
        eq.mark_enrichment_deferred(bill.id, 60.0)
        started = eq.queue_downstream_enrichments(
            bill, source="rss", analyzer=self._analyzer()
        )
        self.assertFalse(started)

    def test_skips_and_defers_when_quota_low(self):
        bill = self._bill()
        started = eq.queue_downstream_enrichments(
            bill, source="backfill", analyzer=self._analyzer(remaining=1)
        )
        self.assertFalse(started)
        self.assertTrue(eq.enrichment_is_deferred(bill.id))

    @patch("services.enrichment_queue.bill_work_lease.try_acquire", return_value=False)
    def test_skips_when_lease_held(self, _acq):
        bill = self._bill()
        started = eq.queue_downstream_enrichments(
            bill, source="routes", analyzer=self._analyzer()
        )
        self.assertFalse(started)

    @patch("services.enrichment_queue.threading.Thread")
    @patch("services.enrichment_queue.bill_work_lease.try_acquire", return_value=True)
    def test_starts_worker_when_ok(self, acq, thread_cls):
        bill = self._bill()
        thread = MagicMock()
        thread_cls.return_value = thread

        started = eq.queue_downstream_enrichments(
            bill, source="rss", analyzer=self._analyzer()
        )

        self.assertTrue(started)
        acq.assert_called_once()
        self.assertEqual(acq.call_args[0][1], "enrich")
        thread_cls.assert_called_once()
        thread.start.assert_called_once()


class TestMaybeQueueEnrichments(unittest.TestCase):
    def setUp(self):
        with eq._enrichment_defer_lock:
            eq._enrichment_defer_until.clear()

    def tearDown(self):
        with eq._enrichment_defer_lock:
            eq._enrichment_defer_until.clear()

    def test_skips_partial(self):
        bill = MagicMock()
        bill.id = 1
        with patch.object(eq, "queue_downstream_enrichments") as q:
            self.assertFalse(
                eq.maybe_queue_enrichments(
                    bill,
                    {**pending_enrichment_stubs()},
                    source="rss",
                    is_partial=True,
                )
            )
            q.assert_not_called()

    def test_skips_when_enrichments_ready(self):
        bill = MagicMock()
        bill.id = 1
        data = {
            "policy_analysis": {"status": "ready"},
            "stakeholders": {"status": "ready"},
        }
        with patch.object(eq, "queue_downstream_enrichments") as q:
            self.assertFalse(
                eq.maybe_queue_enrichments(bill, data, source="backfill")
            )
            q.assert_not_called()

    def test_queues_when_pending_stubs(self):
        bill = MagicMock()
        bill.id = 9
        data = {"summary": "x", **pending_enrichment_stubs()}
        with patch.object(eq, "queue_downstream_enrichments", return_value=True) as q:
            self.assertTrue(
                eq.maybe_queue_enrichments(bill, data, source="rss")
            )
            q.assert_called_once()
            self.assertEqual(q.call_args.kwargs["source"], "rss")


class TestOrchestratorEnrichmentHooks(unittest.TestCase):
    """Light checks that RSS invokes maybe_queue after core success / heal."""

    def _ctx(self):
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=None)
        ctx.__exit__ = MagicMock(return_value=False)
        return ctx

    def _orch_for_analyze(self):
        from services.workflow_orchestrator import WorkflowOrchestrator

        orch = WorkflowOrchestrator.__new__(WorkflowOrchestrator)
        orch.logger = MagicMock()
        orch.ai_analyzer = MagicMock()
        orch.is_running = True
        orch._analysis_holder = "rss:test"
        orch.stats = {
            "total_chunks_analyzed": 0,
            "total_text_processed": 0,
            "analysis_methods": {},
            "processing_times": {
                "total_analysis_time": 0,
                "fastest_analysis": 999,
                "slowest_analysis": 0,
                "average_analysis_time": 0,
            },
            "bills_analyzed": 0,
            "hidden_provisions_detected": 0,
            "suspicious_chunks_found": 0,
            "hidden_detection_methods": {"ai_analysis": 0},
            "high_risk_bills": 0,
            "medium_risk_bills": 0,
        }
        orch._update_analysis_statistics = MagicMock()
        orch.ai_analyzer.get_quota_info.return_value = {
            "status": {
                "is_at_limit": False,
                "is_approaching_limit": False,
            }
        }
        orch.ai_analyzer.model_name = "gemini-test"
        return orch

    def test_rss_queues_after_non_partial_success(self):
        orch = self._orch_for_analyze()
        bill = MagicMock()
        bill.id = 55
        bill.title = "T"
        bill.get_bill_identifier.return_value = "119-HR55"
        bill.get_active_ai_analysis.return_value = None
        bill.get_full_text.return_value = "x" * 100
        orch.ai_analyzer.analyze_bill.return_value = {
            "chunks_analyzed": 1,
            "analysis_method": "single_pass_full_text",
            "is_partial": False,
            **pending_enrichment_stubs(),
        }

        with patch("app.app") as mock_app, patch(
            "services.workflow_orchestrator.Bill"
        ) as BillMod, patch(
            "services.workflow_orchestrator.bill_work_lease.try_acquire",
            return_value=True,
        ), patch(
            "services.workflow_orchestrator.bill_work_lease.release",
        ), patch(
            "services.enrichment_queue.maybe_queue_enrichments"
        ) as maybe_q:
            mock_app.app_context.return_value = self._ctx()
            BillMod.query.get.return_value = bill
            ok, _meta, analyzed = orch._perform_ai_analysis(bill)

        self.assertTrue(ok)
        self.assertTrue(analyzed)
        maybe_q.assert_called()
        self.assertEqual(maybe_q.call_args.kwargs.get("source"), "rss")

    def test_rss_skips_queue_on_partial(self):
        orch = self._orch_for_analyze()
        bill = MagicMock()
        bill.id = 56
        bill.title = "T"
        bill.get_bill_identifier.return_value = "119-HR56"
        bill.get_active_ai_analysis.return_value = None
        bill.get_full_text.return_value = "x" * 100
        orch.ai_analyzer.analyze_bill.return_value = {
            "chunks_analyzed": 1,
            "analysis_method": "map_reduce_macro_chunks",
            "is_partial": True,
            **pending_enrichment_stubs(),
        }

        with patch("app.app") as mock_app, patch(
            "services.workflow_orchestrator.Bill"
        ) as BillMod, patch(
            "services.workflow_orchestrator.bill_work_lease.try_acquire",
            return_value=True,
        ), patch(
            "services.workflow_orchestrator.bill_work_lease.release",
        ), patch(
            "services.enrichment_queue.maybe_queue_enrichments"
        ) as maybe_q:
            mock_app.app_context.return_value = self._ctx()
            BillMod.query.get.return_value = bill
            orch._perform_ai_analysis(bill)

        maybe_q.assert_not_called()

    def test_rss_queues_on_already_analyzed_with_pending(self):
        orch = self._orch_for_analyze()
        pending = {"summary": "done", **pending_enrichment_stubs()}
        active = MagicMock()
        active.get_analysis_data.return_value = pending
        bill = MagicMock()
        bill.id = 57
        bill.get_bill_identifier.return_value = "119-HR57"
        bill.get_active_ai_analysis.return_value = active

        with patch("app.app") as mock_app, patch(
            "services.workflow_orchestrator.Bill"
        ) as BillMod, patch(
            "services.workflow_orchestrator.bill_sync._tier_b_needs_resume_local",
            return_value=False,
        ), patch(
            "services.workflow_orchestrator.bill_work_lease.try_acquire",
            return_value=True,
        ) as acq, patch(
            "services.enrichment_queue.maybe_queue_enrichments"
        ) as maybe_q:
            mock_app.app_context.return_value = self._ctx()
            BillMod.query.get.return_value = bill
            ok, _meta, analyzed = orch._perform_ai_analysis(bill)

        self.assertTrue(ok)
        self.assertFalse(analyzed)
        maybe_q.assert_called_once()
        self.assertEqual(maybe_q.call_args.kwargs.get("source"), "rss")
        acq.assert_not_called()


if __name__ == "__main__":
    unittest.main()
