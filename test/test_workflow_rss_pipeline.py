"""Unit tests for post-unification RSS / workflow pipeline (mocked Congress + Gemini)."""
import importlib.util
import inspect
import unittest
from datetime import datetime
from unittest import mock


def _make_orchestrator():
    """Build WorkflowOrchestrator with heavy deps mocked."""
    with mock.patch(
        "services.workflow_orchestrator.PersistentRSSMonitor"
    ), mock.patch(
        "services.workflow_orchestrator.get_shared_ai_analyzer"
    ) as MockGetAnalyzer, mock.patch(
        "services.workflow_orchestrator.get_shared_congress_api"
    ) as mock_get_api, mock.patch(
        "services.workflow_orchestrator.bill_work_lease.try_acquire",
        return_value=True,
    ), mock.patch(
        "services.workflow_orchestrator.bill_work_lease.release",
    ):
        mock_api = mock.Mock()
        mock_get_api.return_value = mock_api
        mock_analyzer = MockGetAnalyzer.return_value
        mock_analyzer.get_quota_info.return_value = {
            "status": {"is_at_limit": False, "is_approaching_limit": False},
            "current_usage": {
                "requests_this_minute": 0,
                "max_requests_per_minute": 15,
                "safe_remaining_requests": 15,
                "percentage_used": 0,
            },
        }
        from services.workflow_orchestrator import WorkflowOrchestrator

        orch = WorkflowOrchestrator()
        orch.ai_analyzer = mock_analyzer
        orch.congress_api = mock_api
        orch.is_running = True
        return orch


class ExtractBillInfoUrlTest(unittest.TestCase):
    """All eight bill types via congress.gov URL slugs."""

    URL_CASES = [
        ("https://www.congress.gov/bill/119th-congress/house-bill/1", "hr", 1),
        ("https://www.congress.gov/bill/119th-congress/senate-bill/99", "s", 99),
        (
            "https://www.congress.gov/bill/119th-congress/house-resolution/50",
            "hres",
            50,
        ),
        (
            "https://www.congress.gov/bill/119th-congress/senate-resolution/10",
            "sres",
            10,
        ),
        (
            "https://www.congress.gov/bill/119th-congress/house-joint-resolution/5",
            "hjres",
            5,
        ),
        (
            "https://www.congress.gov/bill/119th-congress/senate-joint-resolution/3",
            "sjres",
            3,
        ),
        (
            "https://www.congress.gov/bill/119th-congress/house-concurrent-resolution/7",
            "hconres",
            7,
        ),
        (
            "https://www.congress.gov/bill/119th-congress/senate-concurrent-resolution/2",
            "sconres",
            2,
        ),
    ]

    def test_all_eight_types_from_url(self):
        orch = _make_orchestrator()
        for link, expected_type, expected_number in self.URL_CASES:
            with self.subTest(link=link):
                info = orch._extract_bill_info(
                    {"title": "ignored when URL matches", "link": link}
                )
                self.assertIsNotNone(info)
                self.assertEqual(info["bill_type"], expected_type)
                self.assertEqual(info["bill_number"], expected_number)
                self.assertEqual(info["congress"], 119)


class ExtractBillInfoTitleTest(unittest.TestCase):
    """Title fallback when URL has no recognizable slug."""

    TITLE_CASES = [
        ("H.Res. 100 - Something", "hres", 100),
        ("S.J.Res. 4 - Joint", "sjres", 4),
        ("H.Con.Res. 12 - Concurrent", "hconres", 12),
        ("S.Con.Res. 8 - Concurrent", "sconres", 8),
        ("H.J.Res. 15 - Joint", "hjres", 15),
        ("S.Res. 20 - Simple", "sres", 20),
        ("H.R. 7008 - House bill", "hr", 7008),
        ("S. 123 - Senate bill", "s", 123),
    ]

    def test_title_patterns(self):
        orch = _make_orchestrator()
        for title, expected_type, expected_number in self.TITLE_CASES:
            with self.subTest(title=title):
                info = orch._extract_bill_info(
                    {
                        "title": title,
                        "link": "https://www.congress.gov/bill/119/something",
                    }
                )
                self.assertIsNotNone(info, msg=f"failed for {title}")
                self.assertEqual(info["bill_type"], expected_type)
                self.assertEqual(info["bill_number"], expected_number)
                self.assertEqual(info["congress"], 119)


class QueueDedupeTest(unittest.TestCase):
    def test_duplicate_rss_items_enqueue_once(self):
        orch = _make_orchestrator()
        item = {
            "title": "H.R. 1 - One Big Beautiful Bill",
            "link": "https://www.congress.gov/bill/119th-congress/house-bill/1",
            "published": "Wed, 05 Aug 2026 12:00:00 GMT",
        }
        orch._handle_new_rss_item(item)
        orch._handle_new_rss_item(item)
        self.assertEqual(len(orch.workflow_queue), 1)
        self.assertIn("119-hr-1", orch._queued_bill_keys)
        self.assertEqual(orch.stats["rss_items_processed"], 1)


class FetchAndStoreBillTest(unittest.TestCase):
    def test_calls_bill_sync_with_refresh_and_copies_flags(self):
        from services.bill_sync import SyncResult
        from services.workflow_orchestrator import WorkflowItem, WorkflowStatus

        orch = _make_orchestrator()
        fake_bill = mock.Mock(id=42)
        fake_bill.get_bill_identifier.return_value = "119-HR1"
        result = SyncResult(
            bill=fake_bill,
            created=False,
            actions_added=2,
            status_changed=True,
            reason="workflow:rss",
        )
        item = WorkflowItem(
            bill_identifier="119-HR1",
            congress=119,
            bill_type="hr",
            bill_number=1,
            title="H.R. 1",
            source="rss",
            discovered_at=datetime.utcnow(),
            status=WorkflowStatus.PENDING,
        )

        ctx = mock.MagicMock()
        ctx.__enter__ = mock.Mock(return_value=None)
        ctx.__exit__ = mock.Mock(return_value=False)

        with mock.patch("app.app") as mock_app:
            mock_app.app_context.return_value = ctx
            with mock.patch(
                "services.workflow_orchestrator.bill_sync.sync_bill",
                return_value=result,
            ) as mock_sync:
                bill = orch._fetch_and_store_bill(item)

        self.assertIs(bill, fake_bill)
        self.assertEqual(item.sync_actions_added, 2)
        self.assertTrue(item.sync_status_changed)
        self.assertFalse(item.sync_created)
        kwargs = mock_sync.call_args.kwargs
        self.assertTrue(kwargs.get("refresh_activity_flag"))
        self.assertFalse(kwargs.get("allow_content_ingest"))


class PerformAiAnalysisTest(unittest.TestCase):
    def test_skip_when_complete_analysis_exists(self):
        orch = _make_orchestrator()
        bill = mock.Mock(id=10, title="T")
        bill.get_bill_identifier.return_value = "119-HR10"
        active = mock.Mock()
        active.get_analysis_data.return_value = {
            "is_partial": False,
            "analysis_method": "single_pass_full_text",
            "analysis_tier": "A",
        }
        bill.get_active_ai_analysis.return_value = active

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
                    "services.workflow_orchestrator.bill_sync._tier_b_needs_resume_local",
                    return_value=False,
                ):
                    success, metadata, ran = orch._perform_ai_analysis(bill)

        self.assertTrue(success)
        self.assertIsNone(metadata)
        self.assertFalse(ran)
        orch.ai_analyzer.analyze_bill.assert_not_called()

    def test_runs_analyze_bill_with_bill_object(self):
        orch = _make_orchestrator()
        bill = mock.Mock(id=11, title="Act")
        bill.get_bill_identifier.return_value = "119-HR11"
        bill.get_active_ai_analysis.return_value = None
        bill.get_full_text.return_value = "FULL TEXT BODY " * 20
        orch.ai_analyzer.analyze_bill.return_value = {
            "chunks_analyzed": 1,
            "analysis_method": "single_pass_full_text",
        }
        orch._update_analysis_statistics = mock.Mock()

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
                    return_value=True,
                ), mock.patch(
                    "services.workflow_orchestrator.bill_work_lease.release",
                ):
                    success, metadata, ran = orch._perform_ai_analysis(bill)

        self.assertTrue(success)
        self.assertTrue(ran)
        self.assertIsNotNone(metadata)
        orch.ai_analyzer.analyze_bill.assert_called_once()
        call_args = orch.ai_analyzer.analyze_bill.call_args
        self.assertIs(call_args[0][0], bill)
        self.assertTrue(call_args.kwargs.get("allow_budget_waits", True))

    def test_skip_when_lease_held(self):
        orch = _make_orchestrator()
        bill = mock.Mock(id=12, title="T")
        bill.get_bill_identifier.return_value = "119-HR12"
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
                    success, metadata, ran = orch._perform_ai_analysis(bill)

        self.assertFalse(success)
        self.assertFalse(ran)
        self.assertEqual(metadata.get("skipped_reason"), "lease_held")
        orch.ai_analyzer.analyze_bill.assert_not_called()


class NotifyGateTest(unittest.TestCase):
    def _make_item(self, **flags):
        from services.workflow_orchestrator import WorkflowItem, WorkflowStatus

        item = WorkflowItem(
            bill_identifier="119-HR1",
            congress=119,
            bill_type="hr",
            bill_number=1,
            title="H.R. 1",
            source="rss",
            discovered_at=datetime.utcnow(),
            status=WorkflowStatus.PENDING,
        )
        for k, v in flags.items():
            setattr(item, k, v)
        return item

    def test_unchanged_bill_skips_notification(self):
        orch = _make_orchestrator()
        bill = mock.Mock(id=1)
        bill.get_bill_identifier.return_value = "119-HR1"
        item = self._make_item(
            sync_created=False,
            sync_actions_added=0,
            sync_status_changed=False,
        )

        with mock.patch.object(
            orch, "_fetch_and_store_bill", return_value=bill
        ):
            with mock.patch.object(
                orch,
                "_perform_ai_analysis",
                return_value=(True, None, False),
            ):
                with mock.patch(
                    "services.notification_helper.trigger_bill_analysis_notification"
                ) as mock_notify:
                    orch._process_workflow_item(item)

        mock_notify.assert_not_called()
        self.assertFalse(item.alerts_generated)

    def test_actions_added_triggers_notification(self):
        orch = _make_orchestrator()
        bill = mock.Mock(id=2)
        bill.get_bill_identifier.return_value = "119-HR1"
        item = self._make_item(sync_actions_added=3)

        with mock.patch.object(
            orch, "_fetch_and_store_bill", return_value=bill
        ):
            with mock.patch.object(
                orch,
                "_perform_ai_analysis",
                return_value=(True, None, False),
            ):
                with mock.patch(
                    "services.notification_helper.trigger_bill_analysis_notification"
                ) as mock_notify:
                    orch._process_workflow_item(item)

        mock_notify.assert_called_once_with(2)
        self.assertTrue(item.alerts_generated)

    def test_analysis_ran_triggers_notification(self):
        orch = _make_orchestrator()
        bill = mock.Mock(id=3)
        bill.get_bill_identifier.return_value = "119-HR1"
        item = self._make_item()

        with mock.patch.object(
            orch, "_fetch_and_store_bill", return_value=bill
        ):
            with mock.patch.object(
                orch,
                "_perform_ai_analysis",
                return_value=(True, {"chunks_analyzed": 1}, True),
            ):
                with mock.patch(
                    "services.notification_helper.trigger_bill_analysis_notification"
                ) as mock_notify:
                    orch._process_workflow_item(item)

        mock_notify.assert_called_once_with(3)


class WiringTest(unittest.TestCase):
    def test_no_workflow_bill_processor_import(self):
        import services.workflow_orchestrator as wo

        src = inspect.getsource(wo)
        self.assertNotIn("WorkflowBillProcessor", src)
        self.assertNotIn("workflow_bill_processor", src)
        self.assertIsNone(
            importlib.util.find_spec("services.workflow_bill_processor")
        )

    def test_uses_shared_congress_api(self):
        import services.workflow_orchestrator as wo

        self.assertIn("get_shared_congress_api", inspect.getsource(wo))
        orch = _make_orchestrator()
        self.assertIsNotNone(orch.congress_api)


if __name__ == "__main__":
    unittest.main()
