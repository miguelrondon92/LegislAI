"""Tests for shared bill_sync: resolve, action dedupe, activity refresh, TTL gate."""
import unittest
from datetime import datetime, timedelta
from unittest import mock


class ResolveActiveBillTest(unittest.TestCase):
    def test_orders_active_display_ready_id(self):
        from services import bill_sync

        with mock.patch("db_models.Bill") as MockBill:
            q = MockBill.query.filter_by.return_value
            ordered = q.order_by.return_value
            ordered.first.return_value = "bill"
            result = bill_sync.resolve_active_bill(119, "HR", 1)
            MockBill.query.filter_by.assert_called_once_with(
                congress=119, bill_type="hr", bill_number=1
            )
            self.assertEqual(result, "bill")
            # order_by must be called (active, display_ready, id)
            self.assertTrue(q.order_by.called)


class NeedsActivityRefreshTest(unittest.TestCase):
    def test_missing_last_updated_needs_refresh(self):
        from services import bill_sync

        bill = mock.Mock(last_updated=None)
        self.assertTrue(bill_sync.needs_activity_refresh(bill, ttl_hours=6))

    def test_recent_last_updated_skips(self):
        from services import bill_sync

        bill = mock.Mock(last_updated=datetime.utcnow())
        self.assertFalse(bill_sync.needs_activity_refresh(bill, ttl_hours=6))

    def test_stale_last_updated_needs_refresh(self):
        from services import bill_sync

        bill = mock.Mock(
            last_updated=datetime.utcnow() - timedelta(hours=7)
        )
        self.assertTrue(bill_sync.needs_activity_refresh(bill, ttl_hours=6))


class SyncBillActionsDedupeTest(unittest.TestCase):
    def test_skips_existing_action_and_adds_new(self):
        from services import bill_sync

        bill = mock.Mock()
        bill.id = 42
        bill.get_bill_identifier.return_value = "119-HR1"

        existing = mock.Mock()
        action_list = [
            {
                "actionDate": "2026-01-01",
                "text": "Introduced in House",
                "sourceSystem": {"name": "House"},
            },
            {
                "actionDate": "2026-02-01",
                "text": "Passed House",
                "sourceSystem": {"name": "House"},
            },
        ]

        def _filter_by(**kwargs):
            q = mock.Mock()
            # First call finds existing; subsequent miss
            if kwargs.get("action_text") == "Introduced in House":
                q.first.return_value = existing
            else:
                q.first.return_value = None
            return q

        with mock.patch("app.db") as mock_db:
            with mock.patch("db_models.BillAction") as MockAction:
                MockAction.query.filter_by.side_effect = _filter_by
                MockAction.side_effect = lambda **kwargs: mock.Mock(**kwargs)

                added = bill_sync.sync_bill_actions(bill, action_list)

        self.assertEqual(added, 1)
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()

    def test_repeat_refresh_adds_zero(self):
        from services import bill_sync

        bill = mock.Mock(id=7)
        bill.get_bill_identifier.return_value = "119-S1"
        action_list = [
            {"actionDate": "2026-01-01", "text": "Introduced in Senate"},
        ]

        with mock.patch("app.db"):
            with mock.patch("db_models.BillAction") as MockAction:
                MockAction.query.filter_by.return_value.first.return_value = mock.Mock()
                added = bill_sync.sync_bill_actions(bill, action_list)

        self.assertEqual(added, 0)


class RefreshActivityNoVersionForkTest(unittest.TestCase):
    def test_refresh_updates_status_without_process_bill_data(self):
        from services import bill_sync

        bill = mock.Mock()
        bill.id = 9
        bill.congress = 119
        bill.bill_type = "hr"
        bill.bill_number = 9
        bill.status = "Introduced in House"
        bill.last_action_date = datetime(2026, 1, 1)
        bill.get_bill_identifier.return_value = "119-HR9"
        bill.display_ready = True
        bill.version = 1

        api = mock.Mock()
        api.get_bill_actions.return_value = {
            "actions": [
                {
                    "actionDate": "2026-03-01",
                    "text": "Passed House",
                    "sourceSystem": {"name": "House"},
                }
            ]
        }

        with mock.patch(
            "services.bill_sync.sync_bill_actions", return_value=1
        ) as mock_sync:
            with mock.patch("app.db") as mock_db:
                with mock.patch(
                    "services.congress_api.get_shared_congress_api",
                    return_value=api,
                ):
                    with mock.patch(
                        "services.bill_processor.BillProcessor.process_bill_data"
                    ) as mock_process:
                        added, changed = bill_sync.refresh_activity(
                            bill, congress_api=api
                        )

        self.assertEqual(added, 1)
        self.assertTrue(changed)
        self.assertEqual(bill.status, "Passed House")
        mock_process.assert_not_called()
        mock_sync.assert_called_once()
        mock_db.session.commit.assert_called()
        # display_ready untouched by refresh
        self.assertTrue(bill.display_ready)
        self.assertEqual(bill.version, 1)


class ShouldRefreshForBackfillTest(unittest.TestCase):
    def test_terminal_old_skips(self):
        from services import bill_sync

        bill = mock.Mock(
            status="Became Public Law No: 119-1",
            last_action_date=datetime.utcnow() - timedelta(days=90),
        )
        self.assertFalse(bill_sync.should_refresh_for_backfill(bill))

    def test_non_terminal_refreshes(self):
        from services import bill_sync

        bill = mock.Mock(
            status="Referred to the Committee on Ways and Means",
            last_action_date=datetime.utcnow() - timedelta(days=90),
        )
        self.assertTrue(bill_sync.should_refresh_for_backfill(bill))


class SyncBillCreatedNeedsAnalysisTest(unittest.TestCase):
    def test_missing_bill_ingest_sets_needs_analysis(self):
        from services import bill_sync

        fake_bill = mock.Mock()
        fake_bill.id = 1
        fake_bill.get_active_ai_analysis.return_value = None

        processor = mock.Mock()
        processor.process_bill_data.return_value = fake_bill
        api = mock.Mock()
        api.get_bill_details.return_value = {
            "congress": 119,
            "type": "hr",
            "number": 50,
            "title": "Test",
        }

        ctx = mock.MagicMock()
        ctx.__enter__ = mock.Mock(return_value=None)
        ctx.__exit__ = mock.Mock(return_value=False)

        with mock.patch("app.app") as mock_app:
            mock_app.app_context.return_value = ctx
            with mock.patch(
                "services.bill_sync.resolve_active_bill",
                side_effect=[None, fake_bill],
            ):
                result = bill_sync.sync_bill(
                    119,
                    "hr",
                    50,
                    reason="test",
                    refresh_activity_flag=False,
                    congress_api=api,
                    bill_processor=processor,
                )

        self.assertTrue(result.created)
        self.assertTrue(result.needs_analysis)
        self.assertIs(result.bill, fake_bill)


class ContentMayBeStaleTest(unittest.TestCase):
    def test_missing_bill_is_stale(self):
        from services import bill_sync

        self.assertTrue(bill_sync.content_may_be_stale(None, "2026-01-01"))

    def test_missing_full_text_is_stale(self):
        from services import bill_sync

        bill = mock.Mock(full_text=None, synced_congress_update_date="2026-01-01")
        self.assertTrue(bill_sync.content_may_be_stale(bill, "2026-01-01"))

    def test_matching_update_date_not_stale_without_backfill_visit(self):
        """RSS/search stamp alone is enough — no backfill visit required."""
        from services import bill_sync

        bill = mock.Mock(
            full_text="text",
            synced_congress_update_date="2026-01-15T00:00:00",
            backfill_last_visited_at=None,
        )
        self.assertFalse(bill_sync.content_may_be_stale(bill, "2026-01-15"))

    def test_newer_congress_update_is_stale(self):
        from services import bill_sync

        bill = mock.Mock(
            full_text="text",
            synced_congress_update_date="2026-01-01T00:00:00",
        )
        self.assertTrue(bill_sync.content_may_be_stale(bill, "2026-02-01"))


class CatalogWindowTest(unittest.TestCase):
    def test_fetch_window_uses_introduced_asc_and_respects_count(self):
        from services.backfill_orchestrator import (
            BackfillConfig,
            BackfillOrchestrator,
            ProcessingMode,
        )
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "services.backfill_orchestrator.get_shared_congress_api"
            ) as mock_get, mock.patch(
                "services.backfill_orchestrator.get_shared_ai_analyzer"
            ), mock.patch(
                "services.backfill_orchestrator.BillProcessor"
            ):
                api = mock_get.return_value
                api._make_request.return_value = {
                    "bills": [
                        {
                            "congress": 119,
                            "number": "1",
                            "type": "hr",
                            "title": "A",
                            "url": "u1",
                            "updateDate": "2026-01-01",
                        },
                        {
                            "congress": 119,
                            "number": "2",
                            "type": "hr",
                            "title": "B",
                            "url": "u2",
                            "updateDate": "2026-01-02",
                        },
                        {
                            "congress": 119,
                            "number": "3",
                            "type": "hr",
                            "title": "C",
                            "url": "u3",
                            "updateDate": "2026-01-03",
                        },
                    ]
                }
                orch = BackfillOrchestrator(
                    BackfillConfig(
                        congress_session=119,
                        processing_mode=ProcessingMode.FULL_PROCESSING,
                        congress_api_delay=0,
                    ),
                    state_file=Path(tmp) / "bf.json",
                )
                window = orch.fetch_catalog_window(start_index=0, count=2)

        self.assertEqual(len(window), 2)
        params = api._make_request.call_args[0][1]
        self.assertEqual(params["sort"], "introducedDate+asc")
        self.assertEqual(params["offset"], 0)
        self.assertEqual(window[0]["catalog_index"], 0)
        self.assertEqual(window[1]["catalog_index"], 1)

    def test_resolve_start_index_explicit_overrides_cursor(self):
        from services.backfill_orchestrator import (
            BackfillConfig,
            BackfillOrchestrator,
            ProcessingMode,
        )
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch(
                "services.backfill_orchestrator.get_shared_congress_api"
            ), mock.patch(
                "services.backfill_orchestrator.get_shared_ai_analyzer"
            ), mock.patch(
                "services.backfill_orchestrator.BillProcessor"
            ):
                orch = BackfillOrchestrator(
                    BackfillConfig(
                        congress_session=119,
                        processing_mode=ProcessingMode.FULL_PROCESSING,
                        start_index=4,
                        continue_from_cursor=True,
                    ),
                    state_file=Path(tmp) / "bf.json",
                )
                self.assertEqual(orch._resolve_start_index(), 4)


if __name__ == "__main__":
    unittest.main()
