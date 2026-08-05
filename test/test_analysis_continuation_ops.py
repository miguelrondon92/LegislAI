"""Unit tests for async analysis continuation + provider_model stamping helpers."""
import unittest
from unittest import mock


class ImmediateThread:
    """Run thread targets synchronously for unit tests."""

    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        if self._target:
            self._target()


class ForceContinueAnalysisTest(unittest.TestCase):
    def test_force_continue_reanalyzes_when_analysis_exists(self):
        from routes import _perform_analysis_if_needed

        bill = mock.Mock()
        bill.ai_analysis = {"legacy": True}
        bill.get_active_ai_analysis.return_value = mock.Mock()
        bill.get_full_text.return_value = "Enough text for analysis"
        bill.get_bill_identifier.return_value = "119-HR40"
        bill.title = "Test Bill"
        bill.id = 40

        with mock.patch("routes.ai_analyzer") as mock_analyzer:
            mock_analyzer.analyze_bill.return_value = {
                "summary": {"main_summary": "ok"},
                "is_partial": False,
                "completion_percentage": 100.0,
                "provider_model": "gemini-3.5-flash-lite",
            }
            _perform_analysis_if_needed(bill, force_continue=True)
            mock_analyzer.analyze_bill.assert_called_once_with(
                bill, bill.title, allow_budget_waits=False
            )

    def test_without_force_continue_skips_existing_analysis(self):
        from routes import _perform_analysis_if_needed

        bill = mock.Mock()
        bill.ai_analysis = {"legacy": True}
        bill.get_active_ai_analysis.return_value = mock.Mock()
        bill.get_full_text.return_value = "text"
        bill.get_bill_identifier.return_value = "119-HR41"
        bill.title = "Test Bill"

        with mock.patch("routes.ai_analyzer") as mock_analyzer:
            _perform_analysis_if_needed(bill, force_continue=False)
            mock_analyzer.analyze_bill.assert_not_called()

    @mock.patch("services.ops_alert_service.notify_gemini_failure")
    @mock.patch("threading.Thread", ImmediateThread)
    def test_async_wrapper_reports_continuation_finished(self, mock_notify):
        from services.ops_alert_service import CONTINUATION_FINISHED
        from routes import _perform_analysis_async

        bill = mock.Mock()
        bill.id = 55
        bill.get_bill_identifier.return_value = "119-HR55"

        fresh = mock.Mock()
        fresh.id = 55
        fresh.get_bill_identifier.return_value = "119-HR55"
        active = mock.Mock()
        active.provider_model = "gemini-3.5-flash-lite"
        active.get_analysis_data.return_value = {
            "is_partial": False,
            "completion_percentage": 100.0,
        }
        fresh.get_active_ai_analysis.return_value = active

        ctx = mock.MagicMock()
        ctx.__enter__.return_value = None
        ctx.__exit__.return_value = None

        with mock.patch("routes.app") as mock_app:
            mock_app.app_context.return_value = ctx
            with mock.patch("db_models.Bill") as MockBill:
                MockBill.query.get.return_value = fresh
                with mock.patch("routes._perform_analysis_if_needed") as mock_perf:
                    with mock.patch("routes.ai_analyzer") as mock_analyzer:
                        mock_analyzer.model_name = "gemini-3.5-flash-lite"
                        mock_analyzer.get_rate_limit_status.return_value = {
                            "time_until_reset": 0
                        }
                        import routes as routes_mod
                        with routes_mod._analyzing_lock:
                            routes_mod._analyzing_bill_ids.discard(55)
                        _perform_analysis_async(bill, force_continue=True)
                        mock_perf.assert_called_once_with(
                            fresh, force_continue=True, allow_budget_waits=False
                        )

        finished_calls = [
            c
            for c in mock_notify.call_args_list
            if c.args and c.args[0] == CONTINUATION_FINISHED
        ]
        self.assertTrue(finished_calls, "expected continuation_finished notify")
        kwargs = finished_calls[0].kwargs
        self.assertEqual(kwargs.get("severity"), "info")
        self.assertEqual(kwargs.get("extra", {}).get("event"), "finished")


class ProviderModelCreateHelpersTest(unittest.TestCase):
    def test_create_new_analysis_version_passes_provider_model(self):
        from utils.constants import GEMINI_MODEL

        bill = mock.Mock()
        bill.id = 99

        captured = {}

        def capture_ai_analysis(**kwargs):
            captured.update(kwargs)
            inst = mock.Mock()
            inst.set_analysis_data = mock.Mock()
            return inst

        with mock.patch("db_models.AIAnalysis") as MockAI:
            MockAI.query.filter_by.return_value.order_by.return_value.first.return_value = None
            MockAI.side_effect = capture_ai_analysis
            with mock.patch("db_models.db") as mock_db:
                # Bind real method from Bill class
                from db_models import Bill

                Bill.create_new_analysis_version(
                    bill,
                    analysis_data={"provider_model": "gemini-test-model", "is_partial": False},
                    complexity_score=0.1,
                    controversy_score=0.2,
                    analysis_method="chunked",
                    chunks_analyzed=1,
                    processing_time=0.5,
                    provider_model="gemini-test-model",
                )

        self.assertEqual(captured.get("provider_model"), "gemini-test-model")
        mock_db.session.add.assert_called()
        mock_db.session.commit.assert_called()

    def test_create_new_summary_version_defaults_gemini_model(self):
        from utils.constants import GEMINI_MODEL
        from db_models import Bill

        bill = mock.Mock()
        bill.id = 100
        captured = {}

        def capture_summary(**kwargs):
            captured.update(kwargs)
            inst = mock.Mock()
            inst.set_key_provisions = mock.Mock()
            return inst

        with mock.patch("db_models.Summary") as MockSummary:
            MockSummary.query.filter_by.return_value.order_by.return_value.first.return_value = None
            MockSummary.side_effect = capture_summary
            with mock.patch("db_models.db"):
                Bill.create_new_summary_version(
                    bill,
                    summary_text="hello",
                    plain_language_summary="hi",
                )

        self.assertEqual(captured.get("provider_model"), GEMINI_MODEL)


if __name__ == "__main__":
    unittest.main()
