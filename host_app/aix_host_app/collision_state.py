from __future__ import annotations

from dataclasses import dataclass

from .models import MotionEvent, PneumaticStatusEvent


@dataclass(frozen=True)
class ProtectionReadiness:
    allowed: bool
    reason: str


def protection_readiness(
    event: PneumaticStatusEvent, require_vision: bool
) -> ProtectionReadiness:
    if not event.automatic_enabled:
        return ProtectionReadiness(False, "自动模式关闭")
    if not event.pressure_valid or event.pressure_age_ms > 200:
        return ProtectionReadiness(False, "压力无效或过期")
    if not event.pump_verified:
        return ProtectionReadiness(False, "泵自检未通过")
    if not event.valve_verified:
        return ProtectionReadiness(False, "阀自检未通过")
    if event.self_test_failed:
        return ProtectionReadiness(False, "气动自检失败")
    if require_vision and not event.vision_fresh:
        return ProtectionReadiness(False, "视觉结果过期")
    return ProtectionReadiness(True, "安全条件有效")


class CollisionEventTracker:
    def __init__(self) -> None:
        self.last_seq: int | None = None
        self.last_count: int | None = None
        self.legacy = False

    def observe(self, event: MotionEvent) -> int:
        restarted = self.last_seq is not None and event.seq <= self.last_seq
        if restarted:
            self.last_count = None
            self.legacy = False
        self.last_seq = event.seq

        if event.impact_count is None:
            new_events = int(event.impact and not self.legacy)
            self.legacy = event.impact
            self.last_count = None
            return new_events

        if self.last_count is None:
            self.last_count = event.impact_count
            self.legacy = False
            return int(event.impact_event)

        new_events = (event.impact_count - self.last_count) & 0xFFFFFFFF
        self.last_count = event.impact_count
        self.legacy = False
        return new_events
