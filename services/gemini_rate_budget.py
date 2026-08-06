"""Process-wide FIFO Gemini RPM/TPM budget with optional cross-process DB ceiling."""
from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Deque, Dict, Optional

logger = logging.getLogger(__name__)

# Match EnhancedAIAnalyzer free-tier defaults
DEFAULT_MAX_RPM = 15
DEFAULT_MAX_TPM = 250_000
DEFAULT_USABLE_TPM = 220_000

_shared_budget = None
_shared_budget_lock = threading.Lock()


def get_shared_gemini_budget() -> "GeminiRateBudget":
    global _shared_budget
    with _shared_budget_lock:
        if _shared_budget is None:
            _shared_budget = GeminiRateBudget()
        return _shared_budget


def reset_shared_gemini_budget_for_tests() -> "GeminiRateBudget":
    """Replace the singleton (unit tests only)."""
    global _shared_budget
    with _shared_budget_lock:
        _shared_budget = GeminiRateBudget()
        return _shared_budget


class GeminiRateBudget:
    """
    Shared RPM/TPM window with FIFO admit queue (in-process).

    Cross-process: counters are also persisted to gemini_rate_budget_state so
    Flask + CLI backfill share the same ceiling (not FIFO fairness).
    """

    def __init__(
        self,
        max_requests_per_minute: int = DEFAULT_MAX_RPM,
        max_input_tokens_per_minute: int = DEFAULT_MAX_TPM,
        usable_tpm_headroom: int = DEFAULT_USABLE_TPM,
        persist_to_db: bool = True,
    ):
        self.max_requests_per_minute = max_requests_per_minute
        self.max_input_tokens_per_minute = max_input_tokens_per_minute
        self.usable_tpm_headroom = usable_tpm_headroom
        self.persist_to_db = persist_to_db

        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._queue: Deque[str] = deque()

        self.requests_this_minute = 0
        self.tokens_this_minute = 0
        self.minute_start_time: Optional[float] = None
        self.request_count = 0
        self.last_request_time: Optional[float] = None

    def _reset_window_if_needed_unlocked(self) -> None:
        now = time.time()
        if not self.minute_start_time or now - self.minute_start_time >= 60:
            self.minute_start_time = now
            self.requests_this_minute = 0
            self.tokens_this_minute = 0

    def _seconds_until_reset_unlocked(self) -> float:
        if not self.minute_start_time:
            return 0.0
        return max(0.0, 60.0 - (time.time() - self.minute_start_time))

    def _can_admit_unlocked(self, estimated_tokens: int) -> bool:
        self._reset_window_if_needed_unlocked()
        if self.requests_this_minute >= self.max_requests_per_minute:
            return False
        projected = self.tokens_this_minute + max(0, estimated_tokens)
        if projected > self.usable_tpm_headroom:
            return False
        return True

    def _pull_from_db_unlocked(self) -> None:
        if not self.persist_to_db:
            return
        try:
            from db_models import GeminiRateBudgetState

            row = GeminiRateBudgetState.query.get(1)
            if not row:
                return
            now = time.time()
            db_start = float(row.minute_start_epoch or 0)
            # Same minute window: take the higher usage so we never under-count
            if db_start and now - db_start < 60:
                if (
                    not self.minute_start_time
                    or abs(self.minute_start_time - db_start) < 60
                ):
                    self.minute_start_time = min(
                        self.minute_start_time or db_start, db_start
                    )
                    self.requests_this_minute = max(
                        self.requests_this_minute, int(row.requests_this_minute or 0)
                    )
                    self.tokens_this_minute = max(
                        self.tokens_this_minute, int(row.tokens_this_minute or 0)
                    )
            elif db_start and now - db_start >= 60:
                # Remote window expired; local reset will handle
                pass
        except Exception:
            # No app context / table missing — in-process only
            pass

    def _push_to_db_unlocked(self) -> None:
        if not self.persist_to_db:
            return
        try:
            from db_models import GeminiRateBudgetState, db

            row = GeminiRateBudgetState.query.get(1)
            if not row:
                row = GeminiRateBudgetState(
                    id=1,
                    minute_start_epoch=self.minute_start_time or time.time(),
                    requests_this_minute=self.requests_this_minute,
                    tokens_this_minute=self.tokens_this_minute,
                    updated_at=datetime.utcnow(),
                )
                db.session.add(row)
            else:
                row.minute_start_epoch = self.minute_start_time or time.time()
                row.requests_this_minute = self.requests_this_minute
                row.tokens_this_minute = self.tokens_this_minute
                row.updated_at = datetime.utcnow()
            db.session.commit()
        except Exception:
            try:
                from db_models import db

                db.session.rollback()
            except Exception:
                pass

    def _record_unlocked(self, estimated_tokens: int) -> bool:
        self._pull_from_db_unlocked()
        if not self._can_admit_unlocked(estimated_tokens):
            return False
        self.requests_this_minute += 1
        self.tokens_this_minute += max(0, estimated_tokens)
        self.request_count += 1
        self.last_request_time = time.time()
        self._push_to_db_unlocked()
        return True

    def check_blocked(self, estimated_tokens: int = 0) -> bool:
        """True if we cannot take another request right now."""
        with self._lock:
            self._pull_from_db_unlocked()
            return not self._can_admit_unlocked(estimated_tokens)

    def record(self, estimated_tokens: int = 0) -> bool:
        with self._lock:
            return self._record_unlocked(estimated_tokens)

    def wait_for_capacity(
        self,
        estimated_tokens: int = 0,
        *,
        max_waits: int = 2,
    ) -> bool:
        """
        FIFO wait until this caller is head and budget can accept tokens.
        Does not record — caller must record/admit separately.
        """
        ticket = str(uuid.uuid4())
        with self._cond:
            self._queue.append(ticket)
            waits_used = 0
            try:
                while True:
                    self._pull_from_db_unlocked()
                    self._reset_window_if_needed_unlocked()
                    is_head = self._queue and self._queue[0] == ticket
                    if is_head and self._can_admit_unlocked(estimated_tokens):
                        self._queue.popleft()
                        self._cond.notify_all()
                        return True

                    if is_head and not self._can_admit_unlocked(estimated_tokens):
                        if waits_used >= max_waits:
                            self._queue.remove(ticket)
                            self._cond.notify_all()
                            return False
                        wait_s = self._seconds_until_reset_unlocked()
                        if wait_s <= 0:
                            self.minute_start_time = time.time()
                            self.requests_this_minute = 0
                            self.tokens_this_minute = 0
                            waits_used += 1
                            self._push_to_db_unlocked()
                            continue
                        self._cond.wait(timeout=min(wait_s, 10.0))
                        if self._seconds_until_reset_unlocked() <= 0:
                            self.minute_start_time = time.time()
                            self.requests_this_minute = 0
                            self.tokens_this_minute = 0
                            waits_used += 1
                            self._push_to_db_unlocked()
                        continue

                    self._cond.wait(timeout=1.0)
            except Exception:
                if ticket in self._queue:
                    self._queue.remove(ticket)
                self._cond.notify_all()
                raise

    def admit(
        self,
        estimated_tokens: int = 0,
        *,
        wait: bool = True,
        max_waits: int = 2,
    ) -> bool:
        """
        FIFO admit for one Gemini call. Records on success.

        wait=False: fail immediately if not head-of-queue with budget.
        wait=True: stay in queue until admitted or max_waits minute resets exhausted.
        """
        ticket = str(uuid.uuid4())
        with self._cond:
            self._queue.append(ticket)
            waits_used = 0
            try:
                while True:
                    self._pull_from_db_unlocked()
                    self._reset_window_if_needed_unlocked()

                    is_head = self._queue and self._queue[0] == ticket
                    if is_head and self._can_admit_unlocked(estimated_tokens):
                        ok = self._record_unlocked(estimated_tokens)
                        if ok:
                            self._queue.popleft()
                            self._cond.notify_all()
                            return True

                    if not wait:
                        self._queue.remove(ticket)
                        self._cond.notify_all()
                        return False

                    if is_head and not self._can_admit_unlocked(estimated_tokens):
                        if waits_used >= max_waits:
                            self._queue.remove(ticket)
                            self._cond.notify_all()
                            return False
                        wait_s = self._seconds_until_reset_unlocked()
                        if wait_s <= 0:
                            self.minute_start_time = time.time()
                            self.requests_this_minute = 0
                            self.tokens_this_minute = 0
                            waits_used += 1
                            self._push_to_db_unlocked()
                            continue
                        logger.info(
                            "⏳ Gemini budget: waiting %.1fs for minute reset "
                            "(wait %s/%s, queue depth %s)",
                            wait_s,
                            waits_used + 1,
                            max_waits,
                            len(self._queue),
                        )
                        self._cond.wait(timeout=min(wait_s, 10.0))
                        if self._seconds_until_reset_unlocked() <= 0:
                            self.minute_start_time = time.time()
                            self.requests_this_minute = 0
                            self.tokens_this_minute = 0
                            waits_used += 1
                            self._push_to_db_unlocked()
                        continue

                    # Not head — wait for notify
                    self._cond.wait(timeout=1.0)
            except Exception:
                if ticket in self._queue:
                    self._queue.remove(ticket)
                self._cond.notify_all()
                raise

    def wait_for_reset(self) -> None:
        """Block until current minute window ends, then zero counters."""
        with self._cond:
            self._pull_from_db_unlocked()
            wait_s = self._seconds_until_reset_unlocked()
            while wait_s > 0:
                chunk = min(10.0, wait_s)
                self._cond.wait(timeout=chunk)
                wait_s = self._seconds_until_reset_unlocked()
            self.minute_start_time = time.time()
            self.requests_this_minute = 0
            self.tokens_this_minute = 0
            self._push_to_db_unlocked()
            self._cond.notify_all()

    def reset(self) -> None:
        with self._cond:
            self.requests_this_minute = 0
            self.tokens_this_minute = 0
            self.minute_start_time = time.time()
            self.request_count = 0
            self.last_request_time = None
            self._push_to_db_unlocked()
            self._cond.notify_all()

    def status(self) -> Dict:
        with self._lock:
            self._pull_from_db_unlocked()
            self._reset_window_if_needed_unlocked()
            remaining_requests = max(
                0, self.max_requests_per_minute - self.requests_this_minute
            )
            remaining_tokens = max(
                0, self.usable_tpm_headroom - self.tokens_this_minute
            )
            return {
                "requests_this_minute": self.requests_this_minute,
                "max_requests_per_minute": self.max_requests_per_minute,
                "remaining_requests": remaining_requests,
                "tokens_this_minute": self.tokens_this_minute,
                "max_input_tokens_per_minute": self.max_input_tokens_per_minute,
                "usable_tpm_headroom": self.usable_tpm_headroom,
                "remaining_tokens": remaining_tokens,
                "total_requests": self.request_count,
                "time_until_reset": self._seconds_until_reset_unlocked(),
                "is_at_limit": (
                    self.requests_this_minute >= self.max_requests_per_minute
                    or self.tokens_this_minute >= self.usable_tpm_headroom
                ),
                "is_approaching_limit": (
                    self.requests_this_minute >= self.max_requests_per_minute - 2
                ),
                "last_request_time": self.last_request_time,
                "rate_limit_percentage": (
                    (self.requests_this_minute / self.max_requests_per_minute) * 100
                ),
                "safe_remaining_requests": max(0, remaining_requests - 2),
                "queue_depth": len(self._queue),
            }
