"""Owns the PC-side real/demo dispatch gate and its short-lived demo lease."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable


class OperatingModeController:
    REAL = "real"
    DEMO = "demo"
    MIN_LEASE_MS = 5_000
    MAX_LEASE_MS = 60_000

    def __init__(self, *, clock_ms: Callable[[], int] | None = None) -> None:
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._lock = threading.Lock()
        self._mode = self.REAL
        self._session_id = ""
        self._expires_at_ms = 0
        self._reason = "startup"
        self._changed_at_ms = int(self._clock_ms())

    def _now(self, now_ms: int | None) -> int:
        return int(self._clock_ms() if now_ms is None else now_ms)

    def _expire_locked(self, now_ms: int) -> None:
        if self._mode == self.DEMO and now_ms >= self._expires_at_ms:
            self._mode = self.REAL
            self._session_id = ""
            self._expires_at_ms = 0
            self._reason = "lease_expired"
            self._changed_at_ms = now_ms

    @classmethod
    def _lease(cls, lease_ms: int) -> int:
        value = int(lease_ms)
        if not cls.MIN_LEASE_MS <= value <= cls.MAX_LEASE_MS:
            raise ValueError(f"lease_ms must be between {cls.MIN_LEASE_MS} and {cls.MAX_LEASE_MS}")
        return value

    def start(self, session_id: str, *, lease_ms: int = 15_000, now_ms: int | None = None) -> dict:
        if not session_id or len(session_id) > 64:
            return {"accepted": False, "error": "invalid session_id", **self.snapshot(now_ms=now_ms)}
        try:
            lease = self._lease(lease_ms)
        except (TypeError, ValueError) as exc:
            return {"accepted": False, "error": str(exc), **self.snapshot(now_ms=now_ms)}
        current = self._now(now_ms)
        with self._lock:
            self._expire_locked(current)
            if self._mode == self.DEMO and self._session_id != session_id:
                return {"accepted": False, "error": "another demo session is active", **self._snapshot_locked(current)}
            self._mode = self.DEMO
            self._session_id = session_id
            self._expires_at_ms = current + lease
            self._reason = "demo_started"
            self._changed_at_ms = current
            return {"accepted": True, **self._snapshot_locked(current)}

    def heartbeat(self, session_id: str, *, lease_ms: int = 15_000, now_ms: int | None = None) -> dict:
        try:
            lease = self._lease(lease_ms)
        except (TypeError, ValueError) as exc:
            return {"accepted": False, "error": str(exc), **self.snapshot(now_ms=now_ms)}
        current = self._now(now_ms)
        with self._lock:
            self._expire_locked(current)
            if self._mode != self.DEMO or self._session_id != session_id:
                return {"accepted": False, "error": "demo session is not active", **self._snapshot_locked(current)}
            self._expires_at_ms = current + lease
            self._reason = "heartbeat"
            return {"accepted": True, **self._snapshot_locked(current)}

    def end(self, session_id: str, *, now_ms: int | None = None) -> dict:
        current = self._now(now_ms)
        with self._lock:
            self._expire_locked(current)
            if self._mode != self.DEMO or self._session_id != session_id:
                return {"accepted": False, "error": "demo session is not active", **self._snapshot_locked(current)}
            self._mode = self.REAL
            self._session_id = ""
            self._expires_at_ms = 0
            self._reason = "restored_real"
            self._changed_at_ms = current
            return {"accepted": True, **self._snapshot_locked(current)}

    def is_real(self) -> bool:
        with self._lock:
            now_ms = self._now(None)
            self._expire_locked(now_ms)
            return self._mode == self.REAL

    def snapshot(self, *, now_ms: int | None = None) -> dict:
        current = self._now(now_ms)
        with self._lock:
            self._expire_locked(current)
            return self._snapshot_locked(current)

    def _snapshot_locked(self, now_ms: int) -> dict:
        return {
            "mode": self._mode,
            "session_id": self._session_id,
            "lease_remaining_ms": max(0, self._expires_at_ms - now_ms) if self._mode == self.DEMO else 0,
            "reason": self._reason,
            "changed_at_ms": self._changed_at_ms,
        }
