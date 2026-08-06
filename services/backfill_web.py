"""Web-facing controls for BackfillOrchestrator (Flask background thread)."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from services.backfill_orchestrator import (
    BackfillConfig,
    BackfillOrchestrator,
    BackfillStatus,
    ProcessingMode,
)
from services.pipeline_activity_log import get_backfill_activity_log

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_orchestrator: Optional[BackfillOrchestrator] = None
_thread: Optional[threading.Thread] = None
_is_running = False
_last_error: Optional[str] = None


def _activity():
    return get_backfill_activity_log()


def get_backfill_orchestrator() -> Optional[BackfillOrchestrator]:
    return _orchestrator


def is_backfill_running() -> bool:
    with _lock:
        return _is_running and _thread is not None and _thread.is_alive()


def start_backfill_web(
    congress_session: int = 119,
    processing_mode: str = "full_processing",
    resume: bool = True,
    max_bills: Optional[int] = None,
    start_index: Optional[int] = None,
    continue_from_cursor: bool = True,
) -> Dict[str, Any]:
    global _orchestrator, _thread, _is_running, _last_error

    with _lock:
        if _is_running and _thread is not None and _thread.is_alive():
            return {
                "status": "already_running",
                "message": "Backfill is already running",
            }

        try:
            mode = ProcessingMode(processing_mode)
        except ValueError:
            return {
                "status": "error",
                "message": f"Invalid processing_mode: {processing_mode}",
            }

        if max_bills is not None:
            try:
                max_bills = int(max_bills)
            except (TypeError, ValueError):
                return {
                    "status": "error",
                    "message": "max_bills must be an integer",
                }
            if max_bills < 1:
                return {
                    "status": "error",
                    "message": "max_bills must be >= 1",
                }

        if start_index is not None:
            try:
                start_index = int(start_index)
            except (TypeError, ValueError):
                return {
                    "status": "error",
                    "message": "start_index must be an integer",
                }
            if start_index < 0:
                return {
                    "status": "error",
                    "message": "start_index must be >= 0",
                }

        config_kwargs: Dict[str, Any] = {
            "congress_session": int(congress_session),
            "processing_mode": mode,
            "continue_from_cursor": bool(continue_from_cursor),
        }
        if max_bills is not None:
            config_kwargs["max_bills_per_session"] = max_bills
        if start_index is not None:
            config_kwargs["start_index"] = start_index

        config = BackfillConfig(**config_kwargs)
        state_file = (
            Path("logs") / f"backfill_state_{config.congress_session}.json"
        )
        _orchestrator = BackfillOrchestrator(config, state_file=state_file)
        _last_error = None
        _is_running = True

        def _run():
            global _is_running, _last_error
            log = _activity()
            try:
                from app import app

                parts = [
                    f"congress={congress_session}",
                    f"mode={processing_mode}",
                    f"resume={resume}",
                    f"continue_cursor={continue_from_cursor}",
                ]
                if start_index is not None:
                    parts.append(f"start_index={start_index}")
                if max_bills is not None:
                    parts.append(f"max_bills={max_bills}")
                log.append(
                    f"Backfill started ({', '.join(parts)})",
                    level="info",
                )
                with app.app_context():
                    ok = _orchestrator.start_backfill(resume=bool(resume))
                if ok:
                    log.append("Backfill finished successfully", level="info")
                else:
                    status = getattr(_orchestrator.state, "status", "?")
                    if status == BackfillStatus.PAUSED.value:
                        log.append("Backfill paused", level="warning")
                    else:
                        recent = getattr(_orchestrator.state, "errors", None) or []
                        detail = ""
                        if recent:
                            last = recent[-1]
                            detail = f": {last.get('message', last)}"
                        log.append(
                            f"Backfill ended with status={status}{detail}",
                            level="warning",
                        )
                        if recent:
                            _last_error = str(recent[-1].get("message", recent[-1]))
            except Exception as e:
                _last_error = str(e)
                logger.exception("Backfill web thread failed")
                log.append(f"Backfill failed: {e}", level="error")
            finally:
                with _lock:
                    _is_running = False

        _thread = threading.Thread(target=_run, daemon=True, name="backfill-web")
        _thread.start()
        return {
            "status": "success",
            "message": "Backfill started successfully",
        }


def stop_backfill_web() -> Dict[str, Any]:
    with _lock:
        orch = _orchestrator
    if orch is None:
        return {"status": "error", "message": "No backfill instance"}
    try:
        orch.pause()
        _activity().append("Stop requested — pausing after current bill", level="warning")
        return {"status": "success", "message": "Backfill pause requested"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def get_backfill_status_web() -> Dict[str, Any]:
    running = is_backfill_running()
    with _lock:
        orch = _orchestrator
        last_error = _last_error

    payload: Dict[str, Any] = {
        "is_running": running,
        "last_error": last_error,
    }
    if orch is None:
        # Still expose catalog cursor when idle
        try:
            from app import app
            from db_models import BackfillCatalogState

            with app.app_context():
                row = BackfillCatalogState.query.get(119)
                if row:
                    payload["catalog"] = {
                        "next_index": row.next_index,
                        "sort_key": row.sort_key,
                    }
        except Exception:
            pass
        payload.update(
            {
                "status": "not_started",
                "congress_session": None,
                "processing_mode": None,
                "discovery": {},
                "processing": {},
                "errors": {"count": 0, "recent_errors": []},
                "quota": {},
            }
        )
        return payload

    try:
        payload.update(orch.get_status())
    except Exception as e:
        payload["status_error"] = str(e)

    try:
        from services.enhanced_ai_analyzer import get_shared_ai_analyzer

        payload["quota"] = get_shared_ai_analyzer().get_quota_info()
    except Exception:
        payload["quota"] = {}

    return payload


def get_backfill_logs(limit: int = 100):
    return _activity().tail(limit)
