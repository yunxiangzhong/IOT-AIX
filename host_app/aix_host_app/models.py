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
    accel_x_g: float | None = None
    accel_y_g: float | None = None
    accel_z_g: float | None = None
    gyro_x_dps: float | None = None
    gyro_y_dps: float | None = None
    gyro_z_dps: float | None = None
    accel_norm_g: float | None = None
    tilt_deg: float | None = None
    impact: bool = False
    rapid_tilt: bool = False
    danger_latched: bool = False
    calibrated: bool = False


@dataclass(frozen=True)
class PneumaticStatusEvent:
    ts_ms: int
    state: str
    fault: str
    trigger: str
    operation: int
    pump_on: bool
    valve_on: bool
    pressure_kpa: float
    pressure_valid: bool
    pressure_age_ms: int
    vision_state: str
    vision_fresh: bool
    mpu_available: bool
    mpu_calibrated: bool
    impact: bool
    rapid_tilt: bool


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


@dataclass(frozen=True)
class CameraPreviewEvent:
    valid: bool
    url: str
    ip: str
    port: int
    reason: str


@dataclass(frozen=True)
class VisionDepthEvent:
    frame_seq: int
    capture_ts_ms: int
    model: str
    depth_kind: str
    depth_p10: float
    depth_median: float
    confidence_median: float
    latency_ms: float
    valid: bool


@dataclass(frozen=True)
class DetectionBox:
    class_name: str
    score: float
    bbox_norm: tuple[float, float, float, float]
    relative_depth: float
    risk_score: float


@dataclass(frozen=True)
class VisionRiskEvent:
    frame_seq: int
    capture_ts_ms: int
    depth_p10: float
    depth_median: float
    confidence_median: float
    detections: tuple[DetectionBox, ...]
    risk_score: int
    risk_band: str
    dominant_class: str
    reason: str
    latency_ms: float
    valid: bool


@dataclass(frozen=True)
class RiskAckEvent:
    frame_seq: int
    risk_score: int
    risk_band: str
    valid: bool
    stale: bool


@dataclass(frozen=True)
class ActionStatusEvent:
    ts_ms: int
    frame_seq: int
    risk_score: int
    valid: bool
    stale: bool
    action_state: str
    rgb_pattern: str
