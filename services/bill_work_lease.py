"""DB-backed per-bill work leases shared across search, RSS, and backfill."""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

KIND_ANALYZE = "analyze"
KIND_ENRICH = "enrich"

DEFAULT_TTL_ANALYZE = 1200  # 20 minutes — Tier B waves
DEFAULT_TTL_ENRICH = 600  # 10 minutes


def default_holder(prefix: str) -> str:
    return f"{prefix}:{os.getpid()}"


def _now() -> datetime:
    return datetime.utcnow()


def _purge_expired(bill_id: Optional[int] = None, kind: Optional[str] = None) -> int:
    """Delete expired lease rows. Returns number deleted."""
    from db_models import BillWorkLease, db

    q = BillWorkLease.query.filter(BillWorkLease.expires_at < _now())
    if bill_id is not None:
        q = q.filter_by(bill_id=bill_id)
    if kind is not None:
        q = q.filter_by(work_kind=kind)
    rows = q.all()
    for row in rows:
        db.session.delete(row)
    if rows:
        db.session.commit()
    return len(rows)


def try_acquire(
    bill_id: Optional[int],
    kind: str,
    holder: str,
    ttl_seconds: Optional[int] = None,
) -> bool:
    """
    Try to acquire a lease for (bill_id, kind). Returns True on success.
    bill_id None → always True (no lease needed).
    """
    if bill_id is None:
        return True

    from db_models import BillWorkLease, db
    from sqlalchemy.exc import IntegrityError

    if ttl_seconds is None:
        ttl_seconds = (
            DEFAULT_TTL_ANALYZE if kind == KIND_ANALYZE else DEFAULT_TTL_ENRICH
        )

    try:
        _purge_expired(bill_id=bill_id, kind=kind)
        existing = BillWorkLease.query.filter_by(
            bill_id=bill_id, work_kind=kind
        ).first()
        if existing is not None:
            if existing.holder == holder:
                # Re-entrant for same holder: refresh TTL
                existing.expires_at = _now() + timedelta(seconds=ttl_seconds)
                db.session.commit()
                return True
            return False

        row = BillWorkLease(
            bill_id=bill_id,
            work_kind=kind,
            holder=holder,
            acquired_at=_now(),
            expires_at=_now() + timedelta(seconds=ttl_seconds),
        )
        db.session.add(row)
        db.session.commit()
        return True
    except IntegrityError:
        db.session.rollback()
        logger.debug(
            "Lease race for bill_id=%s kind=%s holder=%s", bill_id, kind, holder
        )
        return False
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning(
            "Lease acquire failed bill_id=%s kind=%s: %s", bill_id, kind, e
        )
        return False


def heartbeat(
    bill_id: Optional[int],
    kind: str,
    holder: str,
    ttl_seconds: Optional[int] = None,
) -> bool:
    """Extend expires_at if this holder still owns the lease."""
    if bill_id is None:
        return True

    from db_models import BillWorkLease, db

    if ttl_seconds is None:
        ttl_seconds = (
            DEFAULT_TTL_ANALYZE if kind == KIND_ANALYZE else DEFAULT_TTL_ENRICH
        )

    try:
        row = BillWorkLease.query.filter_by(
            bill_id=bill_id, work_kind=kind, holder=holder
        ).first()
        if not row:
            return False
        row.expires_at = _now() + timedelta(seconds=ttl_seconds)
        db.session.commit()
        return True
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning(
            "Lease heartbeat failed bill_id=%s kind=%s: %s", bill_id, kind, e
        )
        return False


def release(bill_id: Optional[int], kind: str, holder: str) -> None:
    """Release lease if owned by holder. No-op otherwise."""
    if bill_id is None:
        return

    from db_models import BillWorkLease, db

    try:
        row = BillWorkLease.query.filter_by(
            bill_id=bill_id, work_kind=kind, holder=holder
        ).first()
        if not row:
            return
        db.session.delete(row)
        db.session.commit()
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.warning(
            "Lease release failed bill_id=%s kind=%s: %s", bill_id, kind, e
        )


def is_held(bill_id: Optional[int], kind: str) -> bool:
    """True when a non-expired lease exists for (bill_id, kind)."""
    if bill_id is None:
        return False

    from db_models import BillWorkLease

    try:
        _purge_expired(bill_id=bill_id, kind=kind)
        row = BillWorkLease.query.filter_by(
            bill_id=bill_id, work_kind=kind
        ).first()
        return row is not None and row.expires_at >= _now()
    except Exception as e:
        logger.warning("Lease is_held failed bill_id=%s kind=%s: %s", bill_id, kind, e)
        return False


@contextmanager
def acquire(
    bill_id: Optional[int],
    kind: str,
    holder: str,
    ttl_seconds: Optional[int] = None,
) -> Iterator[bool]:
    """Context manager: yields True if acquired; always releases on exit if acquired."""
    ok = try_acquire(bill_id, kind, holder, ttl_seconds=ttl_seconds)
    try:
        yield ok
    finally:
        if ok:
            release(bill_id, kind, holder)
