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
class RiskEvent:
    ts_ms: int
    level: int
    label: str
    reason: str
    source: str
