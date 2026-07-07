from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .analysis import VisionFeatureEvent


class LineWriter(Protocol):
    def write_line(self, line: str) -> bool: ...


@dataclass(frozen=True)
class VisionBridgeStatus:
    last_seq: int
    last_sent_ms: int | None
    failure_count: int


class VisionEventBridge:
    def __init__(self, min_interval_ms: int = 100) -> None:
        self._min_interval_ms = min_interval_ms
        self._last_sent_ms: int | None = None
        self._seq = 0
        self._failure_count = 0

    @property
    def status(self) -> VisionBridgeStatus:
        return VisionBridgeStatus(
            last_seq=self._seq,
            last_sent_ms=self._last_sent_ms,
            failure_count=self._failure_count,
        )

    def maybe_send(self, event: VisionFeatureEvent, writer: LineWriter | None, now_ms: int) -> bool:
        if writer is None:
            return False
        if self._last_sent_ms is not None and now_ms - self._last_sent_ms < self._min_interval_ms:
            return False

        self._seq += 1
        if not writer.write_line(event.to_json_line(self._seq)):
            self._seq -= 1
            self._failure_count += 1
            return False

        self._last_sent_ms = now_ms
        return True
