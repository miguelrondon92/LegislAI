"""Tests for pipeline activity logs and backfill web helpers."""
import unittest
from unittest import mock


class PipelineActivityLogTest(unittest.TestCase):
    def test_append_and_tail(self):
        from services.pipeline_activity_log import PipelineActivityLog

        log = PipelineActivityLog("test", maxlen=5)
        for i in range(7):
            log.append(f"msg-{i}", level="info", bill_identifier="119-HR1")
        tail = log.tail(3)
        self.assertEqual(len(tail), 3)
        self.assertEqual(tail[0]["message"], "msg-4")
        self.assertEqual(tail[-1]["message"], "msg-6")
        self.assertEqual(tail[0]["pipeline"], "test")


class BackfillWebTest(unittest.TestCase):
    def test_already_running(self):
        from services import backfill_web as bw

        with mock.patch.object(bw, "_is_running", True), mock.patch.object(
            bw, "_thread", mock.Mock(is_alive=mock.Mock(return_value=True))
        ):
            result = bw.start_backfill_web(congress_session=119)
            self.assertEqual(result["status"], "already_running")

    def test_stop_without_instance(self):
        from services import backfill_web as bw

        with mock.patch.object(bw, "_orchestrator", None):
            result = bw.stop_backfill_web()
            self.assertEqual(result["status"], "error")

    def test_status_shape_when_idle(self):
        from services import backfill_web as bw

        with mock.patch.object(bw, "_orchestrator", None), mock.patch.object(
            bw, "_is_running", False
        ), mock.patch.object(bw, "_thread", None):
            status = bw.get_backfill_status_web()
            self.assertFalse(status["is_running"])
            self.assertEqual(status["status"], "not_started")

    def test_web_runner_pushes_app_context(self):
        """Background thread must call start_backfill under Flask app context."""
        from flask import has_app_context
        from services import backfill_web as bw

        captured = {}

        def fake_start_backfill(resume=False):
            captured["has_app_context"] = has_app_context()
            return True

        orch = mock.Mock()
        orch.start_backfill.side_effect = fake_start_backfill
        orch.state = mock.Mock(status="complete", errors=[])

        with bw._lock:
            bw._is_running = False
            bw._thread = None
            bw._orchestrator = None

        with mock.patch.object(bw, "BackfillOrchestrator", return_value=orch), mock.patch.object(
            bw, "_activity", return_value=mock.Mock()
        ):
            result = bw.start_backfill_web(
                congress_session=119, processing_mode="full_processing", resume=False
            )
            self.assertEqual(result["status"], "success")
            thread = bw._thread
            self.assertIsNotNone(thread)
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive())

        self.assertTrue(
            captured.get("has_app_context"),
            "start_backfill must run inside app.app_context()",
        )


    def test_start_accepts_max_bills(self):
        from services import backfill_web as bw

        orch = mock.Mock()
        orch.start_backfill.return_value = True
        orch.state = mock.Mock(status="complete", errors=[])

        with bw._lock:
            bw._is_running = False
            bw._thread = None
            bw._orchestrator = None

        with mock.patch.object(bw, "BackfillOrchestrator") as MockOrch, mock.patch.object(
            bw, "_activity", return_value=mock.Mock()
        ), mock.patch.object(bw, "BackfillConfig") as MockConfig:
            MockOrch.return_value = orch
            result = bw.start_backfill_web(
                congress_session=119,
                processing_mode="analysis_only",
                resume=False,
                max_bills=5,
                start_index=3,
                continue_from_cursor=False,
            )
            self.assertEqual(result["status"], "success")
            kwargs = MockConfig.call_args.kwargs
            self.assertEqual(kwargs["max_bills_per_session"], 5)
            self.assertEqual(kwargs["start_index"], 3)
            self.assertFalse(kwargs["continue_from_cursor"])
            thread = bw._thread
            if thread:
                thread.join(timeout=5)

    def test_start_rejects_invalid_max_bills(self):
        from services import backfill_web as bw

        result = bw.start_backfill_web(max_bills=0)
        self.assertEqual(result["status"], "error")
        result = bw.start_backfill_web(max_bills="abc")
        self.assertEqual(result["status"], "error")


class BackfillPauseLoopTest(unittest.TestCase):
    def test_batch_stops_when_paused(self):
        import tempfile
        from pathlib import Path
        from services.backfill_orchestrator import (
            BackfillOrchestrator,
            BackfillStatus,
            ProcessingMode,
            BackfillConfig,
        )

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "bf.json"
            with mock.patch(
                "services.backfill_orchestrator.get_shared_congress_api"
            ), mock.patch(
                "services.backfill_orchestrator.get_shared_ai_analyzer"
            ) as mock_ga, mock.patch(
                "services.backfill_orchestrator.BillProcessor"
            ):
                mock_analyzer = mock_ga.return_value
                mock_analyzer.get_quota_info.return_value = {
                    "status": {"is_at_limit": False, "is_approaching_limit": False}
                }
                orch = BackfillOrchestrator(
                    BackfillConfig(
                        congress_session=119,
                        processing_mode=ProcessingMode.FULL_PROCESSING,
                        batch_size=2,
                        ai_api_delay=0,
                    ),
                    state_file=state_path,
                )
                orch._save_state = mock.Mock()
                orch.state.status = BackfillStatus.PAUSED.value
                orch._process_single_bill = mock.Mock(return_value="analyzed")

                bills = [
                    {
                        "identifier": "119-HR1",
                        "congress": 119,
                        "bill_type": "hr",
                        "bill_number": 1,
                    },
                    {
                        "identifier": "119-HR2",
                        "congress": 119,
                        "bill_type": "hr",
                        "bill_number": 2,
                    },
                ]
                ok = orch._process_bills_batch(bills)
                self.assertFalse(ok)
                orch._process_single_bill.assert_not_called()


class RssOpsSourceTest(unittest.TestCase):
    def test_lease_skip_does_not_notify_ops(self):
        from services.workflow_orchestrator import WorkflowOrchestrator

        with mock.patch(
            "services.workflow_orchestrator.PersistentRSSMonitor"
        ), mock.patch(
            "services.workflow_orchestrator.get_shared_ai_analyzer"
        ) as mock_ga, mock.patch(
            "services.workflow_orchestrator.get_shared_congress_api"
        ):
            mock_ga.return_value.get_quota_info.return_value = {
                "status": {"is_at_limit": False, "is_approaching_limit": False},
                "current_usage": {},
            }
            orch = WorkflowOrchestrator()
            orch.is_running = True
            bill = mock.Mock(id=42, title="T")
            bill.get_bill_identifier.return_value = "119-HR42"
            bill.get_active_ai_analysis.return_value = None

            ctx = mock.MagicMock()
            ctx.__enter__ = mock.Mock(return_value=None)
            ctx.__exit__ = mock.Mock(return_value=False)

            with mock.patch("app.app") as mock_app:
                mock_app.app_context.return_value = ctx
                with mock.patch(
                    "services.workflow_orchestrator.Bill"
                ) as MockBill:
                    MockBill.query.get.return_value = bill
                    with mock.patch(
                        "services.workflow_orchestrator.bill_work_lease.try_acquire",
                        return_value=False,
                    ):
                        with mock.patch(
                            "services.ops_alert_service.notify_gemini_failure"
                        ) as notify:
                            success, meta, ran = orch._perform_ai_analysis(bill)

            self.assertFalse(success)
            self.assertFalse(ran)
            self.assertEqual(meta.get("skipped_reason"), "lease_held")
            notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
