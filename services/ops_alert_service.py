"""
Ops alerts for Gemini / AI analysis failures.

Always persists OpsAlert rows for the in-app logs dashboard.
Optionally POSTs to OPS_ALERT_WEBHOOK_URL (Zapier/Make/n8n -> email) when configured.
Independent of end-user NotificationService / NOTIFICATIONS_ENABLED.
Never includes API keys or secret values in logs or webhook payloads.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

ops_logger = logging.getLogger("legislai.ops.gemini")

# failure_class values
CLIENT_UNAVAILABLE = "client_unavailable"
MODEL_ERROR = "model_error"
QUOTA_EXHAUSTED = "quota_exhausted"
PARTIAL_ANALYSIS = "partial_analysis"
EMPTY_RESULT = "empty_result"
UNKNOWN = "unknown"

_lock = threading.Lock()
_last_sent: Dict[str, float] = {}


def _alerts_enabled() -> bool:
    return os.environ.get("OPS_ALERTS_ENABLED", "true").lower() == "true"


def _webhook_url() -> Optional[str]:
    url = (os.environ.get("OPS_ALERT_WEBHOOK_URL") or "").strip()
    return url or None


def _cooldown_seconds() -> int:
    try:
        return int(os.environ.get("OPS_ALERT_COOLDOWN_SECONDS", "1800"))
    except ValueError:
        return 1800


def _dedup_key(failure_class: str, bill_identifier: Optional[str]) -> str:
    return f"{failure_class}|{bill_identifier or 'no-bill'}"


def _should_send_webhook(failure_class: str, bill_identifier: Optional[str]) -> bool:
    key = _dedup_key(failure_class, bill_identifier)
    now = time.time()
    cooldown = _cooldown_seconds()
    with _lock:
        last = _last_sent.get(key)
        if last is not None and (now - last) < cooldown:
            return False
        _last_sent[key] = now
        return True


def reset_dedup_state() -> None:
    """Clear cooldown state (for tests)."""
    with _lock:
        _last_sent.clear()


def classify_gemini_error(message: str) -> str:
    """Map an error string to a failure_class."""
    text = (message or "").lower()
    if "429" in text or "quota" in text or "resource_exhausted" in text or "rate limit" in text:
        return QUOTA_EXHAUSTED
    if ("404" in text or "not found" in text) and "model" in text:
        return MODEL_ERROR
    if "gemini client not available" in text or "gemini_api_key not found" in text:
        return CLIENT_UNAVAILABLE
    return UNKNOWN


def _sanitize_extra(extra: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not extra:
        return None
    return {
        k: v
        for k, v in extra.items()
        if "key" not in str(k).lower() and "password" not in str(k).lower()
    }


def _persist_ops_alert(
    *,
    failure_class: str,
    message: str,
    severity: str,
    bill_identifier: Optional[str],
    bill_id: Optional[int],
    source: str,
    completion_percentage: Optional[float],
    extra: Optional[Dict[str, Any]],
    webhook_sent: bool = False,
) -> Optional[int]:
    """Insert OpsAlert row; return id or None. Never raises."""
    try:
        from app import app
        from db_models import OpsAlert, db

        with app.app_context():
            row = OpsAlert(
                failure_class=failure_class,
                severity=severity or "error",
                message=message,
                bill_identifier=bill_identifier,
                bill_id=bill_id,
                source=source or "analyzer",
                completion_percentage=completion_percentage,
                is_read=False,
                webhook_sent=bool(webhook_sent),
            )
            if extra:
                row.set_extra(extra)
            db.session.add(row)
            db.session.commit()
            return row.id
    except Exception as e:
        ops_logger.error(f"GEMINI_FAILURE persist failed: {e}")
        try:
            from db_models import db
            db.session.rollback()
        except Exception:
            pass
        return None


def _mark_webhook_sent(alert_id: Optional[int]) -> None:
    if not alert_id:
        return
    try:
        from app import app
        from db_models import OpsAlert, db

        with app.app_context():
            row = OpsAlert.query.get(alert_id)
            if row:
                row.webhook_sent = True
                db.session.commit()
    except Exception as e:
        ops_logger.error(f"GEMINI_FAILURE webhook_sent update failed: {e}")
        try:
            from db_models import db
            db.session.rollback()
        except Exception:
            pass


def report_gemini_failure(
    *,
    failure_class: str,
    message: str,
    severity: str = "error",
    bill_identifier: Optional[str] = None,
    bill_id: Optional[int] = None,
    completion_percentage: Optional[float] = None,
    source: str = "analyzer",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Log a structured Gemini failure, persist OpsAlert, optionally POST webhook.

    Returns status dict for tests.
    """
    clean_extra = _sanitize_extra(extra)
    event = {
        "event": "gemini_failure",
        "severity": severity,
        "failure_class": failure_class,
        "bill_identifier": bill_identifier,
        "bill_id": bill_id,
        "message": message,
        "completion_percentage": completion_percentage,
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if clean_extra:
        event["extra"] = clean_extra

    log_line = (
        f"GEMINI_FAILURE class={failure_class} bill={bill_identifier or '-'} "
        f"source={source} severity={severity} msg={message}"
    )
    if completion_percentage is not None:
        log_line += f" completion={completion_percentage:.1f}%"

    if severity == "warning":
        ops_logger.warning(log_line)
    else:
        ops_logger.error(log_line)

    status = {
        "logged": True,
        "persisted": False,
        "ops_alert_id": None,
        "webhook_attempted": False,
        "webhook_sent": False,
        "skipped_dedup": False,
        "alerts_disabled": False,
    }

    # Always persist for in-app dashboard (even if OPS_ALERTS_ENABLED=false kills webhook)
    alert_id = _persist_ops_alert(
        failure_class=failure_class,
        message=message,
        severity=severity,
        bill_identifier=bill_identifier,
        bill_id=bill_id,
        source=source,
        completion_percentage=completion_percentage,
        extra=clean_extra,
        webhook_sent=False,
    )
    if alert_id:
        status["persisted"] = True
        status["ops_alert_id"] = alert_id

    if not _alerts_enabled():
        status["alerts_disabled"] = True
        return status

    url = _webhook_url()
    if not url:
        return status

    if not _should_send_webhook(failure_class, bill_identifier):
        status["skipped_dedup"] = True
        ops_logger.info(
            f"GEMINI_FAILURE webhook skipped (cooldown) class={failure_class} bill={bill_identifier or '-'}"
        )
        return status

    status["webhook_attempted"] = True
    try:
        resp = requests.post(url, json=event, timeout=5)
        if 200 <= resp.status_code < 300:
            status["webhook_sent"] = True
            _mark_webhook_sent(alert_id)
            ops_logger.info(
                f"GEMINI_FAILURE webhook sent class={failure_class} bill={bill_identifier or '-'} status={resp.status_code}"
            )
        else:
            ops_logger.error(
                f"GEMINI_FAILURE webhook failed class={failure_class} bill={bill_identifier or '-'} "
                f"status={resp.status_code}"
            )
    except Exception as e:
        ops_logger.error(
            f"GEMINI_FAILURE webhook error class={failure_class} bill={bill_identifier or '-'}: {e}"
        )

    return status


def notify_gemini_failure(
    failure_class: str,
    message: str,
    *,
    severity: str = "error",
    bill=None,
    bill_identifier: Optional[str] = None,
    bill_id: Optional[int] = None,
    completion_percentage: Optional[float] = None,
    source: str = "analyzer",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Convenience wrapper that extracts bill identity when a Bill-like object is passed."""
    ident = bill_identifier
    bid = bill_id
    if bill is not None:
        if ident is None and hasattr(bill, "get_bill_identifier"):
            try:
                ident = bill.get_bill_identifier()
            except Exception:
                ident = None
        if bid is None and hasattr(bill, "id"):
            bid = getattr(bill, "id", None)
    return report_gemini_failure(
        failure_class=failure_class,
        message=message,
        severity=severity,
        bill_identifier=ident,
        bill_id=bid,
        completion_percentage=completion_percentage,
        source=source,
        extra=extra,
    )
