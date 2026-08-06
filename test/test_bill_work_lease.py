"""Unit tests for DB-backed bill work leases."""
import unittest
from datetime import datetime, timedelta
from unittest import mock


class BillWorkLeaseApiTest(unittest.TestCase):
    def test_none_bill_id_always_acquires(self):
        from services import bill_work_lease as lease

        self.assertTrue(lease.try_acquire(None, lease.KIND_ANALYZE, "t"))
        self.assertFalse(lease.is_held(None, lease.KIND_ANALYZE))
        lease.release(None, lease.KIND_ANALYZE, "t")  # no-op

    def test_mutual_exclusion(self):
        from services import bill_work_lease as lease

        bill_id = 910001
        row = mock.Mock(
            bill_id=bill_id,
            work_kind=lease.KIND_ANALYZE,
            holder="a",
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        )

        with mock.patch("db_models.BillWorkLease") as MockLease, mock.patch(
            "db_models.db"
        ) as mock_db, mock.patch.object(lease, "_purge_expired", return_value=0):
            # First acquire: no existing
            q = MockLease.query.filter_by.return_value
            q.first.return_value = None
            MockLease.side_effect = lambda **kw: mock.Mock(**kw)
            self.assertTrue(
                lease.try_acquire(bill_id, lease.KIND_ANALYZE, "a")
            )
            mock_db.session.add.assert_called()
            mock_db.session.commit.assert_called()

            # Second acquire: existing other holder
            q.first.return_value = row
            self.assertFalse(
                lease.try_acquire(bill_id, lease.KIND_ANALYZE, "b")
            )

    def test_same_holder_reentrant_refreshes_ttl(self):
        from services import bill_work_lease as lease

        bill_id = 910002
        row = mock.Mock(
            bill_id=bill_id,
            work_kind=lease.KIND_ANALYZE,
            holder="same",
            expires_at=datetime.utcnow() + timedelta(minutes=1),
        )
        with mock.patch("db_models.BillWorkLease") as MockLease, mock.patch(
            "db_models.db"
        ) as mock_db, mock.patch.object(lease, "_purge_expired", return_value=0):
            MockLease.query.filter_by.return_value.first.return_value = row
            self.assertTrue(
                lease.try_acquire(bill_id, lease.KIND_ANALYZE, "same")
            )
            self.assertGreater(
                row.expires_at, datetime.utcnow() + timedelta(minutes=5)
            )
            mock_db.session.commit.assert_called()

    def test_release_only_owner(self):
        from services import bill_work_lease as lease

        bill_id = 910003
        with mock.patch("db_models.BillWorkLease") as MockLease, mock.patch(
            "db_models.db"
        ) as mock_db:
            MockLease.query.filter_by.return_value.first.return_value = None
            lease.release(bill_id, lease.KIND_ANALYZE, "other")
            mock_db.session.delete.assert_not_called()

            row = mock.Mock()
            MockLease.query.filter_by.return_value.first.return_value = row
            lease.release(bill_id, lease.KIND_ANALYZE, "owner")
            mock_db.session.delete.assert_called_once_with(row)

    def test_heartbeat_extends_expires(self):
        from services import bill_work_lease as lease

        bill_id = 910004
        row = mock.Mock(expires_at=datetime.utcnow())
        with mock.patch("db_models.BillWorkLease") as MockLease, mock.patch(
            "db_models.db"
        ) as mock_db:
            MockLease.query.filter_by.return_value.first.return_value = row
            self.assertTrue(
                lease.heartbeat(bill_id, lease.KIND_ANALYZE, "h", ttl_seconds=100)
            )
            self.assertGreater(row.expires_at, datetime.utcnow())
            mock_db.session.commit.assert_called()

    def test_acquire_context_manager_releases(self):
        from services import bill_work_lease as lease

        with mock.patch.object(lease, "try_acquire", return_value=True) as acq, mock.patch.object(
            lease, "release"
        ) as rel:
            with lease.acquire(7, lease.KIND_ENRICH, "ctx") as ok:
                self.assertTrue(ok)
            acq.assert_called_once()
            rel.assert_called_once_with(7, lease.KIND_ENRICH, "ctx")


if __name__ == "__main__":
    unittest.main()
