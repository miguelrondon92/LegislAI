"""
Shared async queue for stakeholder + policy_analysis enrichments.

Used by routes, RSS (WorkflowOrchestrator), and backfill so enrichers are not
UI-only. Does not block display_ready; uses KIND_ENRICH (separate from analyze).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Optional

from services import bill_work_lease
from services.analysis_enrichers import (
    enrichment_quota_ok,
    enrichments_need_work,
)

logger = logging.getLogger(__name__)

# After a real RPM deferral, don't re-queue until local minute resets
_enrichment_defer_until: Dict[Any, float] = {}
_enrichment_defer_lock = threading.Lock()


def enrichment_is_deferred(bill_id) -> bool:
    if bill_id is None:
        return False
    with _enrichment_defer_lock:
        until = _enrichment_defer_until.get(bill_id)
        if until is None:
            return False
        if time.time() >= until:
            _enrichment_defer_until.pop(bill_id, None)
            return False
        return True


def mark_enrichment_deferred(bill_id, reset_seconds: float) -> None:
    if bill_id is None:
        return
    wait = max(5.0, float(reset_seconds or 60.0))
    with _enrichment_defer_lock:
        _enrichment_defer_until[bill_id] = time.time() + wait


def _holder_for_source(source: str) -> str:
    return bill_work_lease.default_holder(f"{source or 'pipeline'}-enrich")


def queue_downstream_enrichments(
    bill,
    *,
    source: str,
    analyzer=None,
) -> bool:
    """
    Queue stakeholder + policy_analysis enrichers after core analysis.

    Returns True if a worker thread was started.
    """
    bill_id = getattr(bill, "id", None)
    bill_ident = None
    try:
        bill_ident = bill.get_bill_identifier()
    except Exception:
        bill_ident = None

    if enrichment_is_deferred(bill_id):
        logger.info(
            "Enrichment deferred (local RPM) for bill id=%s ident=%s source=%s",
            bill_id,
            bill_ident,
            source,
        )
        return False

    if analyzer is None:
        from services.enhanced_ai_analyzer import get_shared_ai_analyzer

        analyzer = get_shared_ai_analyzer()

    ok, remaining, reset_in = enrichment_quota_ok(analyzer)
    if not ok:
        mark_enrichment_deferred(bill_id, reset_in or 60.0)
        logger.info(
            "Enrichment not queued for bill id=%s source=%s: "
            "remaining_requests=%s (local_minute_budget)",
            bill_id,
            source,
            remaining,
        )
        return False

    holder = _holder_for_source(source)
    if not bill_work_lease.try_acquire(
        bill_id, bill_work_lease.KIND_ENRICH, holder
    ):
        logger.info(
            "Enrichment already in flight for bill id=%s source=%s",
            bill_id,
            source,
        )
        return False

    def enrich_worker():
        from app import app
        from db_models import Bill
        from services.analysis_enrichers import run_downstream_enrichments

        try:
            with app.app_context():
                fresh = Bill.query.get(bill_id) if bill_id else None
                if not fresh:
                    return
                logger.info(
                    "Starting downstream enrichments for %s (source=%s)",
                    fresh.get_bill_identifier(),
                    source,
                )
                result = run_downstream_enrichments(
                    fresh, analyzer, source=source
                )
                if isinstance(result, dict) and result.get("enrichments_deferred"):
                    mark_enrichment_deferred(
                        bill_id,
                        result.get("enrichments_retry_after_seconds") or 60.0,
                    )
                logger.info(
                    "Downstream enrichments done for %s (source=%s)",
                    fresh.get_bill_identifier(),
                    source,
                )
        except Exception as e:
            logger.error(
                "Enrichment failed for bill id=%s source=%s: %s",
                bill_id,
                source,
                e,
            )
            import traceback

            logger.error(traceback.format_exc())
        finally:
            try:
                from app import app

                with app.app_context():
                    bill_work_lease.release(
                        bill_id, bill_work_lease.KIND_ENRICH, holder
                    )
            except Exception as release_err:
                logger.warning(
                    "Failed to release enrich lease for bill id=%s: %s",
                    bill_id,
                    release_err,
                )

    threading.Thread(target=enrich_worker, daemon=True).start()
    return True


def maybe_queue_enrichments(
    bill,
    analysis_data: Optional[Dict[str, Any]] = None,
    *,
    source: str,
    analyzer=None,
    is_partial: bool = False,
) -> bool:
    """
    Queue enrichments when core is complete and stubs still need work.

    If analysis_data is omitted, reads the bill's active AIAnalysis.
    """
    if is_partial:
        return False
    if bill is None:
        return False

    data = analysis_data
    if data is None:
        try:
            active = bill.get_active_ai_analysis()
            if active and hasattr(active, "get_analysis_data"):
                data = active.get_analysis_data()
        except Exception:
            data = None

    if not enrichments_need_work(data if isinstance(data, dict) else None):
        return False

    return queue_downstream_enrichments(bill, source=source, analyzer=analyzer)
