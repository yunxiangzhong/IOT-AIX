from __future__ import annotations

from dataclasses import dataclass

from .models import MotionEvent, PneumaticStatusEvent


# Serial loss can span a long interval, but more than 1024 collision events in one
# counter delta indicates corrupted or reordered telemetry rather than real impacts.
MAX_COLLISION_COUNT_DELTA = 1024


@dataclass(frozen=True)
class ProtectionReadiness:
    allowed: bool
    reason: str


def protection_readiness(
    event: PneumaticStatusEvent, require_vision: bool
) -> ProtectionReadiness:
    reasons: list[str] = []
    if not event.automatic_enabled:
        reasons.append("自动模式关闭")
    if not event.pressure_valid or event.pressure_age_ms > 200:
        reasons.append("压力无效或过期")
    if event.fault != "none":
        reasons.append(f"气动故障：{event.fault}")
    if require_vision and not event.vision_fresh:
        reasons.append("视觉结果过期")
    if reasons:
        return ProtectionReadiness(False, "；".join(reasons))
    return ProtectionReadiness(True, "安全条件有效")


class CollisionEventTracker:
    _UINT32_MAX = 0xFFFFFFFF
    _WRAP_PREVIOUS_MIN = 0xFFFF0000
    _WRAP_CURRENT_MAX = 0x0000FFFF

    def __init__(self) -> None:
        self.last_seq: int | None = None
        self.last_count: int | None = None
        self.legacy = False

    def observe(self, event: MotionEvent) -> int:
        if self.last_seq is not None and event.seq == self.last_seq:
            return 0

        restarted = self.last_seq is not None and event.seq < self.last_seq
        if restarted:
            self.last_count = None
            self.legacy = False
        self.last_seq = event.seq

        if event.impact_count is None:
            new_events = int(event.impact and not self.legacy)
            self.legacy = event.impact
            self.last_count = None
            return new_events

        if not self._is_uint32(event.impact_count):
            self.last_count = None
            self.legacy = False
            return int(bool(event.impact_event))

        if self.last_count is None:
            self.last_count = event.impact_count
            self.legacy = False
            return int(event.impact_event)

        if event.impact_count >= self.last_count:
            new_events = event.impact_count - self.last_count
        elif (
            self.last_count >= self._WRAP_PREVIOUS_MIN
            and event.impact_count <= self._WRAP_CURRENT_MAX
        ):
            new_events = event.impact_count + (1 << 32) - self.last_count
        else:
            new_events = int(event.impact_event)
        self.last_count = event.impact_count
        self.legacy = False
        if new_events > MAX_COLLISION_COUNT_DELTA:
            return int(bool(event.impact_event))
        return new_events

    @classmethod
    def _is_uint32(cls, value: object) -> bool:
        return type(value) is int and 0 <= value <= cls._UINT32_MAX
