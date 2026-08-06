"""
Shared bill sync for LegislAI ETL entry points.

Two freshness axes (versioning model unchanged):
  - Activity refresh: append BillAction rows, update status/last_action_date
    on the active Bill row. No Gemini, no content-hash version fork.
  - Content ingest: first-time create or deliberate re-fetch via BillProcessor
    (may fork a new Bill version on content_hash change).

Callers (search, RSS/workflow, backfill) all use sync_bill().
Never sets display_ready — Analysis owns readiness.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

DEFAULT_ACTIVITY_TTL_HOURS = 6

# Terminal-ish status keywords — backfill skips activity refresh when matched
# and last_action_date is older than BACKFILL_RECENT_DAYS.
_TERMINAL_STATUS_KEYWORDS = (
    "became law",
    "became public law",
    "signed by president",
    "vetoed",
    "failed of passage",
    "failed passage",
)
BACKFILL_RECENT_DAYS = 30


@dataclass
class SyncResult:
    bill: Optional[object]  # Bill | None — avoid circular import at type time
    created: bool = False
    actions_added: int = 0
    status_changed: bool = False
    needs_analysis: bool = False
    needs_resume: bool = False
    reason: str = ""

    @property
    def changed(self) -> bool:
        """True when ingest or activity refresh mutated something material."""
        return self.created or self.actions_added > 0 or self.status_changed


def resolve_active_bill(congress, bill_type, bill_number):
    """Prefer active + display-ready + newest id (shared lookup across pipelines)."""
    from db_models import Bill

    return (
        Bill.query.filter_by(
            congress=int(congress),
            bill_type=str(bill_type).lower(),
            bill_number=int(bill_number),
        )
        .order_by(
            Bill.active.desc(),
            Bill.display_ready.desc(),
            Bill.id.desc(),
        )
        .first()
    )


def needs_activity_refresh(bill, *, ttl_hours: float = DEFAULT_ACTIVITY_TTL_HOURS) -> bool:
    """TTL gate for search/detail — True if last_updated is missing or older than TTL."""
    if bill is None:
        return True
    last = getattr(bill, "last_updated", None)
    if last is None:
        return True
    if getattr(last, "tzinfo", None) is not None:
        last = last.replace(tzinfo=None)
    return datetime.utcnow() - last >= timedelta(hours=ttl_hours)


def should_refresh_for_backfill(bill) -> bool:
    """Backfill: refresh non-terminal bills, or any bill with recent last_action_date."""
    if bill is None:
        return True
    status = (getattr(bill, "status", None) or "").lower()
    is_terminal = any(k in status for k in _TERMINAL_STATUS_KEYWORDS)
    last_action = getattr(bill, "last_action_date", None)
    if last_action is not None and getattr(last_action, "tzinfo", None) is not None:
        last_action = last_action.replace(tzinfo=None)
    recent = False
    if last_action is not None:
        recent = datetime.utcnow() - last_action <= timedelta(days=BACKFILL_RECENT_DAYS)
    if is_terminal and not recent:
        return False
    return True


def normalize_congress_update_date(value) -> Optional[str]:
    """Normalize Congress updateDate to a comparable ISO-ish string (date or datetime)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(timespec="seconds")
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None).isoformat(timespec="seconds")
    except Exception:
        # Date-only YYYY-MM-DD still compares lexicographically
        return text[:40]


def _update_date_newer(candidate: Optional[str], known: Optional[str]) -> bool:
    """True if candidate is strictly newer than known (both normalized)."""
    c = normalize_congress_update_date(candidate)
    k = normalize_congress_update_date(known)
    if not c:
        return False
    if not k:
        return True
    return c > k


def content_may_be_stale(bill, congress_update_date=None) -> bool:
    """
    Whether content ingest is warranted.

    Shared across RSS / search / backfill: if another pipeline already stamped
    synced_congress_update_date for this Congress updateDate, backfill must
    not treat the bill as content-stale solely because it never walked it.
    """
    if bill is None:
        return True
    full_text = getattr(bill, "full_text", None)
    if not (full_text and str(full_text).strip()):
        return True
    if _update_date_newer(
        congress_update_date, getattr(bill, "synced_congress_update_date", None)
    ):
        return True
    return False


def stamp_synced_congress_update_date(bill, congress_update_date=None) -> None:
    """Persist shared sync marker when known (caller commits)."""
    if bill is None:
        return
    normalized = normalize_congress_update_date(congress_update_date)
    if not normalized:
        return
    current = getattr(bill, "synced_congress_update_date", None)
    if current is None or _update_date_newer(normalized, current):
        bill.synced_congress_update_date = normalized


def _categorize_action_type(action_text: str) -> str:
    action_text_lower = (action_text or "").lower()
    action_patterns = {
        "introduced": ["introduced", "introduction"],
        "referred": ["referred", "referred to"],
        "reported": ["reported", "reported by"],
        "passed": ["passed", "agreed to", "adopted"],
        "failed": ["failed", "rejected", "not agreed to"],
        "enacted": ["enacted", "became law", "signed"],
        "vetoed": ["vetoed", "veto"],
        "amended": ["amended", "amendment"],
        "scheduled": ["scheduled", "placed on calendar"],
        "hearing": ["hearing", "heard"],
        "markup": ["markup", "marked up"],
        "conference": ["conference", "conferees"],
        "resolved": ["resolved", "resolution"],
        "withdrawn": ["withdrawn", "withdrawal"],
    }
    for action_type, patterns in action_patterns.items():
        if any(pattern in action_text_lower for pattern in patterns):
            return action_type
    return "other"


def _generate_action_description(action_text: str, action_type: str) -> str:
    descriptions = {
        "introduced": "Bill was introduced in Congress",
        "referred": "Bill was referred to committee for review",
        "reported": "Committee reported the bill favorably",
        "passed": "Bill was passed by the chamber",
        "failed": "Bill failed to pass",
        "enacted": "Bill became law",
        "vetoed": "Bill was vetoed by the President",
        "amended": "Bill was amended",
        "scheduled": "Bill was scheduled for consideration",
        "hearing": "Public hearing was held on the bill",
        "markup": "Committee marked up the bill",
        "conference": "Conference committee was formed",
        "resolved": "Differences between chambers were resolved",
        "withdrawn": "Bill was withdrawn from consideration",
        "other": "Other legislative action occurred",
    }
    return descriptions.get(action_type, "Legislative action occurred")


def sync_bill_actions(bill, action_list) -> int:
    """
    Append missing BillAction rows for bill, deduped on
    (bill_id, action_date, action_text). Returns count of newly added actions.
    Does not update bill.status — caller decides (refresh_activity does).
    """
    from app import db
    from db_models import BillAction

    if not bill or not getattr(bill, "id", None):
        return 0
    if not action_list:
        return 0

    added = 0
    for action_data in action_list:
        if not isinstance(action_data, dict):
            continue
        action_date = action_data.get("actionDate")
        action_text = action_data.get("text", "")
        if not action_date or not action_text:
            continue
        try:
            parsed_date = datetime.fromisoformat(action_date + "T00:00:00")
        except Exception:
            continue

        existing = BillAction.query.filter_by(
            bill_id=bill.id,
            action_date=parsed_date,
            action_text=action_text,
        ).first()
        if existing:
            continue

        action_type = _categorize_action_type(action_text)
        source_system = action_data.get("sourceSystem") or {}
        source_system_name = (
            source_system.get("name", "Congress.gov")
            if isinstance(source_system, dict)
            else "Congress.gov"
        )
        bill_action = BillAction(
            bill_id=bill.id,
            action_date=parsed_date,
            action_type=action_type,
            action_text=action_text,
            action_description=_generate_action_description(action_text, action_type),
            source_system="congress_api",
            source_system_name=source_system_name,
        )
        db.session.add(bill_action)
        added += 1

    if added:
        db.session.commit()
        logger.info(
            "sync_bill_actions: added %s actions for %s",
            added,
            bill.get_bill_identifier(),
        )
    return added


def _normalize_action_list(actions_payload) -> list:
    """Congress API returns {'actions': [...]} or a bare list."""
    if not actions_payload:
        return []
    if isinstance(actions_payload, list):
        return actions_payload
    if isinstance(actions_payload, dict) and "actions" in actions_payload:
        return actions_payload.get("actions") or []
    return []


def refresh_activity(bill, *, congress_api=None) -> Tuple[int, bool]:
    """
    Fetch latest actions from Congress and append missing ones.
    Updates status / last_action_date / last_updated on the active row.
    Returns (actions_added, status_changed). Never forks a Bill version.
    """
    from app import db
    from services.congress_api import get_shared_congress_api

    if bill is None:
        return 0, False

    api = congress_api or get_shared_congress_api()
    actions_data = api.get_bill_actions(bill.congress, bill.bill_type, bill.bill_number)
    action_list = _normalize_action_list(actions_data)

    old_status = bill.status
    old_last_action = bill.last_action_date

    actions_added = sync_bill_actions(bill, action_list)

    status_changed = False
    if action_list:
        latest = action_list[0]
        new_status = latest.get("text") or bill.status
        new_date = None
        action_date = latest.get("actionDate")
        if action_date:
            try:
                new_date = datetime.fromisoformat(action_date + "T00:00:00")
            except Exception:
                new_date = None
        if new_status and new_status != old_status:
            bill.status = new_status
            status_changed = True
        if new_date and new_date != old_last_action:
            bill.last_action_date = new_date
            status_changed = True

    bill.last_updated = datetime.utcnow()
    db.session.commit()
    return actions_added, status_changed


def _tier_b_needs_resume_local(analysis_data) -> bool:
    """Mirror routes._tier_b_needs_resume without importing routes."""
    if not analysis_data:
        return False
    method = analysis_data.get("analysis_method") or ""
    tier = analysis_data.get("analysis_tier")
    if not (tier == "B" or method == "map_reduce_macro_chunks"):
        return False
    if analysis_data.get("is_partial"):
        return True
    findings = analysis_data.get("tier_b_map_findings") or []
    if not findings:
        return False
    usable = 0
    for f in findings:
        if not isinstance(f, dict) or f.get("map_failed"):
            continue
        if (f.get("summary") or "").strip() or (f.get("key_provisions") or []):
            usable += 1
    total = int(analysis_data.get("total_chunks_available") or len(findings))
    if usable == 0 or usable < total:
        return True
    sm = ((analysis_data.get("summary") or {}).get("main_summary") or "").lower()
    needles = (
        "mapping error",
        "failed to extract",
        "across all provided chunks",
        "across all chunks",
        "portions failed",
    )
    return any(n in sm for n in needles)


def _analysis_flags(bill) -> Tuple[bool, bool]:
    """Return (needs_analysis, needs_resume) for an existing bill."""
    if bill is None:
        return True, False
    active = bill.get_active_ai_analysis() if hasattr(bill, "get_active_ai_analysis") else None
    if not active:
        return True, False
    data = active.get_analysis_data() if hasattr(active, "get_analysis_data") else None
    if _tier_b_needs_resume_local(data):
        return False, True
    return False, False


def sync_bill(
    congress,
    bill_type,
    bill_number,
    *,
    reason: str = "sync",
    refresh_activity_flag: bool = True,
    allow_content_ingest: bool = False,
    congress_update_date=None,
    congress_api=None,
    bill_processor=None,
) -> SyncResult:
    """
    Unified ETL entry: resolve active bill, optionally refresh activity,
    optionally content-ingest when missing (or when allow_content_ingest).

    Never runs Gemini. Never sets display_ready.
    Stamps synced_congress_update_date from congress_update_date or detail payload
    so RSS / search / backfill share one freshness marker.
    """
    from app import app
    from app import db
    from services.bill_processor import BillProcessor
    from services.congress_api import get_shared_congress_api

    api = congress_api or get_shared_congress_api()
    processor = bill_processor or BillProcessor(congress_api=api)
    seen_update = normalize_congress_update_date(congress_update_date)

    with app.app_context():
        bill = resolve_active_bill(congress, bill_type, bill_number)
        created = False
        actions_added = 0
        status_changed = False
        did_work = False

        if bill is None:
            # First ingest — always allowed
            bill_data = api.get_bill_details(congress, bill_type, bill_number)
            if not bill_data:
                logger.warning(
                    "sync_bill: Congress API miss for %s-%s%s (%s)",
                    congress,
                    bill_type,
                    bill_number,
                    reason,
                )
                return SyncResult(bill=None, reason=reason)
            if not seen_update:
                seen_update = normalize_congress_update_date(
                    bill_data.get("updateDate") or bill_data.get("update_date")
                )
            bill = processor.process_bill_data(bill_data)
            if not bill:
                return SyncResult(bill=None, reason=reason)
            created = True
            did_work = True
        elif allow_content_ingest:
            # Deliberate re-fetch (backfill) — may fork version on content change
            bill_data = api.get_bill_details(congress, bill_type, bill_number)
            if bill_data:
                if not seen_update:
                    seen_update = normalize_congress_update_date(
                        bill_data.get("updateDate") or bill_data.get("update_date")
                    )
                ingested = processor.process_bill_data(bill_data)
                if ingested is not None:
                    # Re-resolve in case a new version row was created
                    bill = resolve_active_bill(congress, bill_type, bill_number) or ingested
                    if getattr(bill, "id", None) != getattr(ingested, "id", None):
                        created = True  # new version row
                    did_work = True
            if refresh_activity_flag and bill is not None:
                actions_added, status_changed = refresh_activity(bill, congress_api=api)
                did_work = True
        elif refresh_activity_flag:
            actions_added, status_changed = refresh_activity(bill, congress_api=api)
            did_work = True

        if did_work and bill is not None:
            try:
                stamp_synced_congress_update_date(bill, seen_update)
                db.session.commit()
            except Exception as e:
                logger.debug(
                    "sync_bill: could not stamp synced_congress_update_date: %s", e
                )
                try:
                    db.session.rollback()
                except Exception:
                    pass

        needs_analysis, needs_resume = _analysis_flags(bill)
        if created:
            needs_analysis = True
            needs_resume = False

        return SyncResult(
            bill=bill,
            created=created,
            actions_added=actions_added,
            status_changed=status_changed,
            needs_analysis=needs_analysis,
            needs_resume=needs_resume,
            reason=reason,
        )


def get_bills_without_analysis(limit: int = 10) -> List:
    """
    Bills with no active AIAnalysis row (workflow backfill queue helper).
    Moved from WorkflowBillProcessor.
    """
    from app import app
    from db_models import AIAnalysis, Bill

    with app.app_context():
        try:
            bills = (
                Bill.query.filter(
                    ~Bill.id.in_(
                        AIAnalysis.query.with_entities(AIAnalysis.bill_id).filter(
                            AIAnalysis.active.is_(True)
                        )
                    )
                )
                .filter(Bill.active.is_(True))
                .limit(limit)
                .all()
            )
            return list(bills)
        except Exception as e:
            logger.error("get_bills_without_analysis failed: %s", e)
            return []
