from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PressureSample:
    seq: int
    ts_ms: int
    raw: int
    mv: int
    kpa: float
    filtered_kpa: float
    over_pressure: bool
    valid: bool
    source: str = "json"


@dataclass(frozen=True)
class VisionFrame:
    frame_id: int
    ts_ms: int
    width: int
    height: int
    source: str


@dataclass(frozen=True)
class MotionEvent:
    seq: int
    ts_ms: int
    speed_mps: float
    accel_mps2: float
    speed_valid: bool
    accel_valid: bool
    source: str = "json"


@dataclass(frozen=True)
class RiskEvent:
    seq: int
    ts_ms: int
    level: int
    target_pct: int
    reason: str
    vision_stale: bool
    pressure_safe: bool
    pressure_state: str = "enabled"


@dataclass(frozen=True)
class ActuatorEvent:
    seq: int
    ts_ms: int
    mode: str
    target_pct: int
    pump: str
    valve: str
