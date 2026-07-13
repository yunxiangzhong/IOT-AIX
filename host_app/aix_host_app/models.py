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
class MotionEvent:
    seq: int
    ts_ms: int
    speed_mps: float
    accel_mps2: float
    speed_valid: bool
    accel_valid: bool
    source: str = "json"


@dataclass(frozen=True)
class CameraStatusEvent:
    seq: int
    ts_ms: int
    sensor: str
    width: int
    height: int
    pixel_format: str
    frame_bytes: int
    fps: float
    frames_ok: int
    capture_failures: int
    psram: bool
    valid: bool
