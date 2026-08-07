"""Unit tests for fast bill ETL: persisted text, no sync AI in processor, async queue."""
import hashlib
import unittest
from datetime import datetime
from unittest import mock


class ImmediateThread:
    def __init__(self, target=None, daemon=None):
        self._target = target

    def start(self):
        if self._target:
            self._target()


class GetFullTextPersistedTest(unittest.TestCase):
    def test_returns_stored_full_text_without_congress(self):
        from db_models import Bill

        bill = Bill(
            congress=119,
            bill_type="hr",
            bill_number=99,
            title="Test",
            summary="Sum",
            full_text="STORED FULL TEXT BODY",
            version=1,
            active=True,
        )
        with mock.patch("services.congress_api.get_shared_congress_api") as mock_get:
            text = bill.get_full_text()
            self.assertEqual(text, "STORED FULL TEXT BODY")
            mock_get.assert_not_called()

    def test_fetch_if_missing_false_skips_api(self):
        from db_models import Bill

        bill = Bill(
            congress=119,
            bill_type="hr",
            bill_number=100,
            title="Test",
            summary="Only summary",
            version=1,
            active=True,
        )
        with mock.patch("services.congress_api.get_shared_congress_api") as mock_get:
            text = bill.get_full_text(fetch_if_missing=False)
            self.assertEqual(text, "Only summary")
            mock_get.assert_not_called()


class ProcessBillDataNoSyncAITest(unittest.TestCase):
    def test_persists_text_and_does_not_call_analyze_bill(self):
        from services.bill_processor import BillProcessor

        processor = BillProcessor(
            congress_api=mock.Mock(),
            ai_analyzer=mock.Mock(),
        )
        processor.ai_analyzer.analyze_bill = mock.Mock()
        processor._process_bill_actions = mock.Mock()

        bill_data = {
            "congress": 119,
            "type": "hr",
            "number": 501,
            "title": "Fast ETL Act",
            "summary": "A summary",
            "full_text": "Section 1. This is the full bill text for hashing.",
            "sponsors": [],
            "actions": {"actions": []},
        }

        fake_bill = mock.Mock()
        fake_bill.id = 1
        fake_bill.version = 1
        fake_bill.get_bill_identifier.return_value = "119-HR501"
        fake_bill.full_text = None

        with mock.patch("db_models.Bill") as MockBill:
            MockBill.query.filter_by.return_value.order_by.return_value.all.return_value = []
            # Constructor returns our fake when Bill(...) is called
            def bill_ctor(**kwargs):
                for k, v in kwargs.items():
                    setattr(fake_bill, k, v)
                return fake_bill

            MockBill.side_effect = bill_ctor
            with mock.patch("services.bill_processor.db") as mock_db:
                with mock.patch(
                    "services.bill_processor.clean_bill_text",
                    side_effect=lambda t: t,
                ):
                    with mock.patch(
                        "services.bill_processor.extract_sections",
                        return_value=["Section 1"],
                    ):
                        result = processor.process_bill_data(bill_data)

        self.assertIs(result, fake_bill)
        self.assertTrue(fake_bill.full_text)
        self.assertTrue(fake_bill.content_hash)
        processor.ai_analyzer.analyze_bill.assert_not_called()
        mock_db.session.add.assert_called()
        mock_db.session.commit.assert_called()

    def test_action_list_defaults_when_actions_missing(self):
        from services.bill_processor import BillProcessor

        processor = BillProcessor(congress_api=mock.Mock(), ai_analyzer=mock.Mock())
        processor.ai_analyzer.analyze_bill = mock.Mock()
        processor._process_bill_actions = mock.Mock()

        bill_data = {
            "congress": 119,
            "type": "hr",
            "number": 502,
            "title": "No Actions Act",
            "summary": "Sum",
            "full_text": "Body text here.",
            # no actions key
        }
        fake_bill = mock.Mock()
        fake_bill.get_bill_identifier.return_value = "119-HR502"

        with mock.patch("db_models.Bill") as MockBill:
            MockBill.query.filter_by.return_value.order_by.return_value.all.return_value = []
            MockBill.side_effect = lambda **kwargs: fake_bill
            with mock.patch("services.bill_processor.db"):
                with mock.patch(
                    "services.bill_processor.clean_bill_text", side_effect=lambda t: t
                ):
                    with mock.patch(
                        "services.bill_processor.extract_sections", return_value=[]
                    ):
                        result = processor.process_bill_data(bill_data)

        self.assertIs(result, fake_bill)
        processor._process_bill_actions.assert_called_once()
        args = processor._process_bill_actions.call_args[0]
        self.assertEqual(args[1], [])


class ColdLoadQueuesAsyncTest(unittest.TestCase):
    @mock.patch("threading.Thread", ImmediateThread)
    def test_search_miss_queues_async_after_process(self):
        from routes import _get_or_fetch_bill_by_number
        from services.bill_sync import SyncResult

        bill = mock.Mock()
        bill.id = 77
        bill.get_bill_identifier.return_value = "119-HR77"
        bill.get_active_ai_analysis.return_value = None
        bill.ai_analysis = None

        sync_result = SyncResult(
            bill=bill,
            created=True,
            needs_analysis=True,
            reason="search",
        )

        with mock.patch(
            "routes.bill_sync.resolve_active_bill", return_value=None
        ):
            with mock.patch(
                "routes.bill_sync.sync_bill", return_value=sync_result
            ) as mock_sync:
                with mock.patch("routes._perform_analysis_async") as mock_async:
                    with mock.patch(
                        "routes._parse_bill_identifier",
                        return_value=(119, "hr", 77),
                    ):
                        with mock.patch(
                            "routes._analysis_is_in_flight", return_value=False
                        ):
                            result = _get_or_fetch_bill_by_number("HR 77", 119)
                    mock_sync.assert_called_once()
                    mock_async.assert_called_once_with(bill, force_continue=False)
                    self.assertIs(result, bill)


class SharedCongressApiTest(unittest.TestCase):
    def test_singleton_same_instance(self):
        import services.congress_api as capi

        # Reset singleton for test isolation
        with capi._shared_congress_lock:
            capi._shared_congress_api = None
        a = capi.get_shared_congress_api()
        b = capi.get_shared_congress_api()
        self.assertIs(a, b)
        with capi._shared_congress_lock:
            capi._shared_congress_api = None


class PrepareBillTextPrefersStoredTest(unittest.TestCase):
    def test_prepare_uses_column_without_get_full_text_fetch(self):
        from services.enhanced_ai_analyzer import EnhancedAIAnalyzer

        analyzer = EnhancedAIAnalyzer.__new__(EnhancedAIAnalyzer)
        bill = mock.Mock()
        bill.title = "T"
        bill.summary = "S"
        bill.full_text = "PERSISTED"
        bill.get_full_text = mock.Mock(return_value="SHOULD_NOT_USE")

        # getattr(bill, "full_text") is truthy so get_full_text should not be needed
        text = EnhancedAIAnalyzer._prepare_bill_text(analyzer, bill)
        self.assertIn("PERSISTED", text)
        bill.get_full_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()
