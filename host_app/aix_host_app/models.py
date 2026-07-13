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
