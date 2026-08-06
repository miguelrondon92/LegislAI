"""In-process ring buffers for RSS / Backfill dashboard activity logs."""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List, Optional


class PipelineActivityLog:
    """Thread-safe ring buffer of structured log lines for a dashboard."""

    def __init__(self, name: str, maxlen: int = 200):
        self.name = name
        self._maxlen = maxlen
        self._entries: Deque[Dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def append(
        self,
        message: str,
        *,
        level: str = "info",
        bill_identifier: Optional[str] = None,
    ) -> None:
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": level,
            "message": message,
            "bill_identifier": bill_identifier,
            "pipeline": self.name,
        }
        with self._lock:
            self._entries.append(entry)

    def tail(self, limit: int = 100) -> List[Dict]:
        limit = max(1, min(int(limit or 100), self._maxlen))
        with self._lock:
            items = list(self._entries)
        if len(items) <= limit:
            return items
        return items[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_rss_log = PipelineActivityLog("rss")
_backfill_log = PipelineActivityLog("backfill")


def get_rss_activity_log() -> PipelineActivityLog:
    return _rss_log


def get_backfill_activity_log() -> PipelineActivityLog:
    return _backfill_log
