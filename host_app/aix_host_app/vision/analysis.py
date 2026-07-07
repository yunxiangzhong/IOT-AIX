from __future__ import annotations

import json
from dataclasses import dataclass

import cv2
import numpy as np

from .camera import CameraFrame


@dataclass(frozen=True)
class VisionFeatureEvent:
    ts_ms: int
    looming: float
    area_rate: float
    center_motion: float
    confidence: float
    valid: bool
    source: str = "pc_camera"
    radial_expansion: float = 0.0

    def to_json_line(self, seq: int) -> str:
        payload = {
            "type": "vision",
            "version": 1,
            "seq": int(seq),
            "ts_ms": int(self.ts_ms),
            "source": self.source,
            "looming": round(_clamp01(self.looming), 3),
            "area_rate": round(_clamp01(self.area_rate), 3),
            "center_motion": round(_clamp01(self.center_motion), 3),
            "confidence": round(_clamp01(self.confidence), 3),
            "valid": bool(self.valid),
        }
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class VisionAnalysisResult:
    scene: str
    targets: str
    risk_level: int
    action: str
    features: VisionFeatureEvent


class NullVisionAnalyzer:
    """Stable placeholder for future road-scene and target detection."""

    def analyze(self, frame: CameraFrame | None) -> VisionAnalysisResult:
        features = VisionFeatureEvent(
            ts_ms=frame.ts_ms if frame is not None else 0,
            looming=0.0,
            area_rate=0.0,
            center_motion=0.0,
            confidence=0.0,
            valid=frame is not None,
        )
        return VisionAnalysisResult(
            scene="实时画面" if frame is not None else "实时画面",
            targets="待接入算法",
            risk_level=0,
            action="保持",
            features=features,
        )


class VisionTrendAnalyzer:
    """PC-camera looming detector based on optical-flow expansion."""

    def __init__(self) -> None:
        self._previous_gray: np.ndarray | None = None
        self._previous_active_ratio = 0.0
        self._smoothed_looming = 0.0

    def analyze(self, frame: CameraFrame | None) -> VisionAnalysisResult:
        if frame is None:
            return self._result(0, 0.0, 0.0, 0.0, 0.0, False, 0.0)

        gray = _preprocess_gray(frame)

        if self._previous_gray is None:
            radial_expansion = 0.0
            center_motion = 0.0
            area_rate = 0.0
            confidence = 0.25
        else:
            flow = cv2.calcOpticalFlowFarneback(
                self._previous_gray,
                gray,
                None,
                0.5,
                3,
                15,
                3,
                5,
                1.2,
                0,
            )
            radial_expansion, center_motion, area_rate, confidence = _flow_features(
                flow,
                self._previous_active_ratio,
            )
            self._previous_active_ratio = _active_ratio(flow)

        raw_looming = _clamp01(
            (0.55 * radial_expansion) +
            (0.30 * center_motion) +
            (0.15 * area_rate)
        )
        self._smoothed_looming = max(raw_looming, (self._smoothed_looming * 0.55) + (raw_looming * 0.45))
        looming = _clamp01(self._smoothed_looming)
        level = _risk_level_from_looming(looming)
        features = VisionFeatureEvent(
            ts_ms=frame.ts_ms,
            looming=looming,
            area_rate=area_rate,
            center_motion=center_motion,
            confidence=confidence,
            valid=True,
            radial_expansion=radial_expansion,
        )

        self._previous_gray = gray
        if self._previous_active_ratio == 0.0:
            self._previous_active_ratio = 0.001

        return VisionAnalysisResult(
            scene="PC摄像头光流趋势",
            targets=(
                f"expand={features.radial_expansion:.2f}, loom={features.looming:.2f}, "
                f"center={features.center_motion:.2f}, area={features.area_rate:.2f}"
            ),
            risk_level=level,
            action="发送视觉特征到 ESP" if level > 0 else "等待 ESP 判断",
            features=features,
        )

    def _result(
        self,
        ts_ms: int,
        looming: float,
        area_rate: float,
        center_motion: float,
        confidence: float,
        valid: bool,
        radial_expansion: float,
    ) -> VisionAnalysisResult:
        features = VisionFeatureEvent(
            ts_ms=ts_ms,
            looming=looming,
            area_rate=area_rate,
            center_motion=center_motion,
            confidence=confidence,
            valid=valid,
            radial_expansion=radial_expansion,
        )
        return VisionAnalysisResult(
            scene="PC摄像头光流趋势",
            targets="无有效画面",
            risk_level=0,
            action="等待 ESP 判断",
            features=features,
        )


def _preprocess_gray(frame: CameraFrame) -> np.ndarray:
    gray = _frame_to_gray(frame).astype(np.uint8)
    gray = cv2.resize(gray, (160, 120), interpolation=cv2.INTER_AREA)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def _frame_to_gray(frame: CameraFrame) -> np.ndarray:
    data = np.frombuffer(frame.rgb_data, dtype=np.uint8)
    if frame.bytes_per_line == frame.width * 3:
        rgb = data.reshape((frame.height, frame.width, 3))
    else:
        rows = data.reshape((frame.height, frame.bytes_per_line))[:, : frame.width * 3]
        rgb = rows.reshape((frame.height, frame.width, 3))
    gray = (0.299 * rgb[:, :, 0]) + (0.587 * rgb[:, :, 1]) + (0.114 * rgb[:, :, 2])
    return gray.astype(np.float32)


def _flow_features(flow: np.ndarray, previous_active_ratio: float) -> tuple[float, float, float, float]:
    height, width = flow.shape[:2]
    flow_x = flow[:, :, 0]
    flow_y = flow[:, :, 1]
    mag = np.sqrt((flow_x * flow_x) + (flow_y * flow_y))

    yy, xx = np.mgrid[0:height, 0:width]
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    rx = xx - cx
    ry = yy - cy
    radius = np.sqrt((rx * rx) + (ry * ry)) + 1e-6
    radial = ((flow_x * rx) + (flow_y * ry)) / radius

    active = mag > max(0.25, float(np.percentile(mag, 72)) * 0.65)
    active_ratio = float(active.mean())
    outward = np.maximum(radial, 0.0)
    inward = np.maximum(-radial, 0.0)

    if active.any():
        radial_signal = float(outward[active].mean() - (inward[active].mean() * 0.45))
        radial_expansion = _clamp01(radial_signal / 2.2)
    else:
        radial_expansion = 0.0

    center = _center_mask(height, width)
    center_mag = float(mag[center].mean()) if center.any() else 0.0
    center_motion = _clamp01(center_mag / 2.8)

    growth = max(0.0, active_ratio - previous_active_ratio)
    area_rate = _clamp01((active_ratio * 1.8) + (growth * 3.5))

    confidence = _clamp01(0.25 + (active_ratio * 1.8) + (center_motion * 0.35) + (radial_expansion * 0.45))
    return radial_expansion, center_motion, area_rate, confidence


def _active_ratio(flow: np.ndarray) -> float:
    mag = np.sqrt((flow[:, :, 0] * flow[:, :, 0]) + (flow[:, :, 1] * flow[:, :, 1]))
    active = mag > max(0.25, float(np.percentile(mag, 72)) * 0.65)
    return float(active.mean())


def _center_mask(height: int, width: int) -> np.ndarray:
    yy, xx = np.mgrid[0:height, 0:width]
    cx = (width - 1) / 2.0
    cy = (height - 1) / 2.0
    rx = np.abs(xx - cx) / max(cx, 1.0)
    ry = np.abs(yy - cy) / max(cy, 1.0)
    return (rx <= 0.55) & (ry <= 0.55)


def _risk_level_from_looming(looming: float) -> int:
    if looming >= 0.90:
        return 100
    if looming >= 0.70:
        return 80
    if looming >= 0.45:
        return 50
    if looming >= 0.25:
        return 20
    return 0


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return float(value)
