"""Unit tests for post-unification backfill orchestrator (mocked Congress + Gemini)."""
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _make_backfill(*, state_file=None, mode=None):
    from services.backfill_orchestrator import (
        BackfillConfig,
        BackfillOrchestrator,
        ProcessingMode,
    )

    config = BackfillConfig(
        congress_session=119,
        processing_mode=mode or ProcessingMode.FULL_PROCESSING,
        batch_size=1,
        max_bills_per_session=10,
    )
    with mock.patch(
        "services.backfill_orchestrator.get_shared_congress_api"
    ) as mock_get, mock.patch(
        "services.backfill_orchestrator.get_shared_ai_analyzer"
    ) as mock_analyzer_get, mock.patch(
        "services.backfill_orchestrator.BillProcessor"
    ), mock.patch(
        "services.backfill_orchestrator.bill_work_lease.try_acquire",
        return_value=True,
    ), mock.patch(
        "services.backfill_orchestrator.bill_work_lease.release",
    ):
        mock_api = mock.Mock()
        mock_get.return_value = mock_api
        orch = BackfillOrchestrator(config, state_file=state_file)
        orch.congress_api = mock_api
        orch.ai_analyzer = mock_analyzer_get.return_value
        return orch, mock_get


class BackfillInitTest(unittest.TestCase):
    def test_uses_shared_congress_api(self):
        orch, mock_get = _make_backfill()
        mock_get.assert_called()
        self.assertIs(orch.congress_api, mock_get.return_value)

    def test_state_file_kwarg_before_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "backfill_state_prod_119.json"
            state_path.write_text(
                "{"
                '"congress_session": 119,'
                '"status": "paused",'
                '"processing_mode": "full_processing",'
                '"start_time": "2026-01-01T00:00:00",'
                '"last_update": null,'
                '"total_bills_discovered": 0,'
                '"bills_discovered": [],'
                '"discovery_offset": 0,'
                '"discovery_complete": false,'
                '"bills_processed": 0,'
                '"bills_analyzed": 0,'
                '"bills_failed": 0,'
                '"current_batch": 0,'
                '"last_processed_bill": null,'
                '"errors": [],'
                '"api_quota_hits": 0,'
                '"stats": {},'
                '"display_ready_start_count": 0,'
                '"display_ready_goal_count": 0,'
                '"bills_made_display_ready": 0'
                "}"
            )
            orch, _ = _make_backfill(state_file=state_path)
            self.assertEqual(orch.state_file, state_path)
            self.assertEqual(orch.state.status, "paused")


class GapAnalysisUsesNewTableTest(unittest.TestCase):
    def test_analyzed_count_uses_get_active_ai_analysis(self):
        from services.backfill_orchestrator import ProcessingMode

        orch, _ = _make_backfill(mode=ProcessingMode.ANALYSIS_ONLY)
        orch.state.discovery_complete = True

        bill_with = mock.Mock(
            display_ready=True,
            ai_analysis=None,  # legacy empty — must NOT count as unanalyzed
        )
        bill_with.get_bill_identifier.return_value = "119-HR1"
        bill_with.get_active_ai_analysis.return_value = mock.Mock()

        bill_without = mock.Mock(display_ready=False, ai_analysis="legacy-json")
        bill_without.get_bill_identifier.return_value = "119-HR2"
        bill_without.get_active_ai_analysis.return_value = None

        ctx = mock.MagicMock()
        ctx.__enter__ = mock.Mock(return_value=None)
        ctx.__exit__ = mock.Mock(return_value=False)

        with mock.patch("services.backfill_orchestrator.app") as mock_app:
            mock_app.app_context.return_value = ctx
            with mock.patch(
                "services.backfill_orchestrator.Bill"
            ) as MockBill:
                MockBill.query.filter_by.return_value.all.return_value = [
                    bill_with,
                    bill_without,
                ]
                gaps = orch.analyze_gaps()

        self.assertEqual(gaps["db_analyzed_bills"], 1)
        self.assertEqual(gaps["unanalyzed_bills"], 1)
        self.assertEqual(orch.state.stats["unanalyzed_bills"], 1)
        self.assertEqual(gaps["status"], "complete")
        self.assertEqual(gaps["unanalyzed_bill_samples"], ["119-HR2"])

    def test_analyze_gaps_orm_stays_inside_app_context(self):
        """get_active_ai_analysis must not run after app_context exits."""
        from services.backfill_orchestrator import ProcessingMode

        orch, _ = _make_backfill(mode=ProcessingMode.ANALYSIS_ONLY)
        orch.state.discovery_complete = True

        call_order = []

        bill = mock.Mock(display_ready=False)
        bill.get_bill_identifier.return_value = "119-HR9"

        def get_analysis():
            call_order.append("orm")
            return None

        bill.get_active_ai_analysis.side_effect = get_analysis

        ctx = mock.MagicMock()

        def enter(_self=None):
            call_order.append("enter")
            return None

        def exit_(_self=None, *exc):
            call_order.append("exit")
            return False

        ctx.__enter__ = enter
        ctx.__exit__ = exit_

        with mock.patch("services.backfill_orchestrator.app") as mock_app:
            mock_app.app_context.return_value = ctx
            with mock.patch(
                "services.backfill_orchestrator.Bill"
            ) as MockBill:
                MockBill.query.filter_by.return_value.all.return_value = [bill]
                gaps = orch.analyze_gaps()

        self.assertEqual(gaps["status"], "complete")
        enter_i = call_order.index("enter")
        exit_i = call_order.index("exit")
        orm_indices = [i for i, x in enumerate(call_order) if x == "orm"]
        self.assertTrue(orm_indices, "expected ORM analysis lookups")
        self.assertTrue(
            all(enter_i < i < exit_i for i in orm_indices),
            f"ORM access outside context: {call_order}",
        )


class ProcessSingleBillTest(unittest.TestCase):
    def test_process_bills_respects_max_bills(self):
        from services.backfill_orchestrator import ProcessingMode

        orch, _ = _make_backfill(mode=ProcessingMode.FULL_PROCESSING)
        orch.config.max_bills_per_session = 2
        orch.state.discovery_complete = True
        orch.state.bills_discovered = [
            {"identifier": f"119-HR{i}", "congress": 119, "bill_type": "hr", "bill_number": i}
            for i in range(1, 6)
        ]
        orch._process_bills_batch = mock.Mock(return_value=True)
        orch._save_state = mock.Mock()

        ok = orch._process_bills({"status": "complete"})
        self.assertTrue(ok)
        passed = orch._process_bills_batch.call_args[0][0]
        self.assertEqual(len(passed), 2)
        self.assertEqual(passed[0]["identifier"], "119-HR1")

    def test_analyzed_counter_not_double_counted(self):
        from services.backfill_orchestrator import (
            BackfillStatus,
            ProcessingMode,
        )

        orch, _ = _make_backfill(mode=ProcessingMode.FULL_PROCESSING)
        orch.config.ai_api_delay = 0
        orch._save_state = mock.Mock()
        orch.state.status = BackfillStatus.PROCESSING.value
        orch.state.bills_processed = 0
        orch.state.bills_analyzed = 0
        orch.state.bills_failed = 0
        orch.ai_analyzer.get_quota_info.return_value = {
            "status": {"is_at_limit": False, "is_approaching_limit": False}
        }
        # Simulate _process_single_bill returning success without its own counter bump
        orch._process_single_bill = mock.Mock(
            side_effect=["analyzed", "already_analyzed", "analyzed"]
        )

        bills = [
            {"identifier": f"119-HR{i}", "congress": 119, "bill_type": "hr", "bill_number": i}
            for i in (1, 2, 3)
        ]
        ok = orch._process_bills_batch(bills)
        self.assertTrue(ok)
        self.assertEqual(orch.state.bills_processed, 3)
        self.assertEqual(orch.state.bills_analyzed, 2)

    def test_fresh_bill_skips_content_ingest_and_gemini(self):
        """RSS/search-synced bill with matching updateDate is not reingested."""
        from services.backfill_orchestrator import ProcessingMode
        from services.bill_sync import SyncResult

        orch, _ = _make_backfill(mode=ProcessingMode.FULL_PROCESSING)
        existing = mock.Mock(
            id=5,
            display_ready=True,
            full_text="BODY",
            synced_congress_update_date="2026-01-01T00:00:00",
            backfill_last_visited_at=None,
        )
        existing.get_active_ai_analysis.return_value = mock.Mock()
        existing.get_bill_identifier.return_value = "119-HR5"

        sync_result = SyncResult(
            bill=existing,
            created=False,
            needs_analysis=False,
            actions_added=0,
            status_changed=False,
            reason="backfill:full_processing",
        )

        bill_info = {
            "identifier": "119-HR5",
            "congress": 119,
            "bill_type": "hr",
            "bill_number": 5,
            "update_date": "2026-01-01",
        }

        ctx = mock.MagicMock()
        ctx.__enter__ = mock.Mock(return_value=None)
        ctx.__exit__ = mock.Mock(return_value=False)

        with mock.patch("services.backfill_orchestrator.app") as mock_app:
            mock_app.app_context.return_value = ctx
            with mock.patch(
                "services.backfill_orchestrator.bill_sync.resolve_active_bill",
                return_value=existing,
            ), mock.patch(
                "services.backfill_orchestrator.bill_sync.content_may_be_stale",
                return_value=False,
            ), mock.patch(
                "services.backfill_orchestrator.bill_sync.should_refresh_for_backfill",
                return_value=False,
            ), mock.patch(
                "services.backfill_orchestrator.bill_sync.sync_bill",
                return_value=sync_result,
            ) as mock_sync, mock.patch(
                "app.db"
            ):
                status = orch._process_single_bill(bill_info)

        self.assertEqual(status, "skipped_fresh")
        kwargs = mock_sync.call_args.kwargs
        self.assertFalse(kwargs.get("allow_content_ingest"))
        orch.ai_analyzer.analyze_bill.assert_not_called()

    def test_missing_bill_syncs_with_content_ingest_then_analyzes(self):
        from services.backfill_orchestrator import ProcessingMode
        from services.bill_sync import SyncResult

        orch, _ = _make_backfill(mode=ProcessingMode.FULL_PROCESSING)
        new_bill = mock.Mock(id=99, display_ready=False, title="New Act")
        new_bill.get_full_text.return_value = "BODY " * 50
        new_bill.get_active_ai_analysis.return_value = None
        new_bill.get_bill_identifier.return_value = "119-HR99"

        sync_result = SyncResult(
            bill=new_bill,
            created=True,
            needs_analysis=True,
            reason="backfill:full_processing",
        )
        orch.ai_analyzer.analyze_bill.return_value = {
            "chunks_analyzed": 1,
            "analysis_method": "single_pass_full_text",
        }

        bill_info = {
            "identifier": "119-HR99",
            "congress": 119,
            "bill_type": "hr",
            "bill_number": 99,
        }

        ctx = mock.MagicMock()
        ctx.__enter__ = mock.Mock(return_value=None)
        ctx.__exit__ = mock.Mock(return_value=False)

        with mock.patch("services.backfill_orchestrator.app") as mock_app:
            mock_app.app_context.return_value = ctx
            with mock.patch(
                "services.backfill_orchestrator.bill_sync.resolve_active_bill",
                return_value=None,
            ):
                with mock.patch(
                    "services.backfill_orchestrator.bill_sync.sync_bill",
                    return_value=sync_result,
                ) as mock_sync:
                    with mock.patch(
                        "services.backfill_orchestrator.bill_work_lease.try_acquire",
                        return_value=True,
                    ), mock.patch(
                        "services.backfill_orchestrator.bill_work_lease.release",
                    ):
                        status = orch._process_single_bill(bill_info)

        self.assertEqual(status, "analyzed")
        kwargs = mock_sync.call_args.kwargs
        self.assertTrue(kwargs.get("allow_content_ingest"))
        orch.ai_analyzer.analyze_bill.assert_called_once()
        call = orch.ai_analyzer.analyze_bill.call_args
        self.assertIs(call[0][0], new_bill)
        self.assertTrue(call.kwargs.get("allow_budget_waits"))

    def test_defers_when_lease_held(self):
        from services.backfill_orchestrator import ProcessingMode
        from services.bill_sync import SyncResult

        orch, _ = _make_backfill(mode=ProcessingMode.FULL_PROCESSING)
        new_bill = mock.Mock(id=100, display_ready=False, title="Held")
        new_bill.get_full_text.return_value = "BODY " * 50
        new_bill.get_active_ai_analysis.return_value = None

        sync_result = SyncResult(
            bill=new_bill,
            created=True,
            needs_analysis=True,
            reason="backfill:full_processing",
        )
        bill_info = {
            "identifier": "119-HR100",
            "congress": 119,
            "bill_type": "hr",
            "bill_number": 100,
        }

        ctx = mock.MagicMock()
        ctx.__enter__ = mock.Mock(return_value=None)
        ctx.__exit__ = mock.Mock(return_value=False)

        with mock.patch("services.backfill_orchestrator.app") as mock_app:
            mock_app.app_context.return_value = ctx
            with mock.patch(
                "services.backfill_orchestrator.bill_sync.resolve_active_bill",
                return_value=None,
            ):
                with mock.patch(
                    "services.backfill_orchestrator.bill_sync.sync_bill",
                    return_value=sync_result,
                ):
                    with mock.patch(
                        "services.backfill_orchestrator.bill_work_lease.try_acquire",
                        return_value=False,
                    ):
                        status = orch._process_single_bill(bill_info)

        self.assertEqual(status, "lease_deferred")
        orch.ai_analyzer.analyze_bill.assert_not_called()


class NoDuplicateCategoryStoreTest(unittest.TestCase):
    def test_process_single_bill_has_no_sneakiness_helper(self):
        from services.backfill_orchestrator import BackfillOrchestrator
        import services.backfill_orchestrator as bo

        src = inspect.getsource(BackfillOrchestrator._process_single_bill)
        self.assertNotIn("_create_category_mappings_with_sneakiness", src)
        self.assertNotIn("_store_hidden_provisions", src)
        self.assertFalse(
            hasattr(
                BackfillOrchestrator, "_create_category_mappings_with_sneakiness"
            )
        )
        self.assertIn("bill_sync", inspect.getsource(bo))


if __name__ == "__main__":
    unittest.main()
