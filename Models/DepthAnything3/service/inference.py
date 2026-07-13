from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class PredictionSummary:
    depth_p10: float
    depth_median: float
    confidence_median: float


@dataclass(frozen=True)
class DepthPrediction:
    depth: np.ndarray
    confidence: np.ndarray


@dataclass(frozen=True)
class DetectionSummary:
    class_name: str
    score: float
    bbox_norm: tuple[float, float, float, float]
    relative_depth: float = -1.0


@dataclass(frozen=True)
class RiskSummary:
    depth_p10: float
    depth_median: float
    confidence_median: float
    detections: list[dict]
    risk_score: int
    risk_band: str
    dominant_class: str
    reason: str


class RiskTracker:
    """Single-stream temporal smoothing and lightweight box-growth tracking."""

    def __init__(self) -> None:
        self._risk: float | None = None
        self._objects: dict[str, tuple[float, int]] = {}

    def reset(self) -> None:
        self._risk = None
        self._objects.clear()

    def smooth(self, raw_score: float) -> float:
        raw_score = float(np.clip(raw_score, 0.0, 100.0))
        if self._risk is None:
            self._risk = raw_score
        else:
            factor = 0.65 if raw_score >= self._risk else 0.25
            self._risk += factor * (raw_score - self._risk)
        return self._risk

    def growth_score(self, class_name: str, area: float, now_ms: int) -> float:
        previous = self._objects.get(class_name)
        self._objects[class_name] = (area, now_ms)
        if previous is None:
            return 0.0
        previous_area, previous_ms = previous
        dt = max((now_ms - previous_ms) / 1000.0, 0.001)
        return float(np.clip(max(0.0, area - previous_area) / dt / 0.15, 0.0, 1.0))


class Da3Engine:
    model_name = "DA3-SMALL"
    device = "cuda"

    def __init__(self, weights: Path, model_loader=None) -> None:
        self._weights = weights
        self._model = (model_loader or self._load_local_model)(weights)

    @staticmethod
    def _load_local_model(weights: Path):
        import torch
        from depth_anything_3.api import DepthAnything3

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the DA3 service")
        model = DepthAnything3.from_pretrained(str(weights))
        return model.to(device="cuda").eval()

    def infer_jpeg(self, image_bytes: bytes) -> PredictionSummary:
        prediction = self.predict_jpeg(image_bytes)
        return summarize_prediction(prediction.depth, prediction.confidence)

    def predict_jpeg(self, image_bytes: bytes) -> DepthPrediction:
        import cv2

        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("JPEG decoding failed")
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        prediction = self._model.inference(
            [image],
            process_res=336,
            export_dir=None,
        )
        return DepthPrediction(depth=prediction.depth[0], confidence=prediction.conf[0])


def summarize_prediction(depth: np.ndarray, confidence: np.ndarray) -> PredictionSummary:
    if depth.size == 0 or confidence.size == 0:
        raise ValueError("prediction arrays must not be empty")
    if not np.isfinite(depth).all() or not np.isfinite(confidence).all():
        raise ValueError("prediction arrays must be finite")

    return PredictionSummary(
        depth_p10=float(np.percentile(depth, 10)),
        depth_median=float(np.median(depth)),
        confidence_median=float(np.median(confidence)),
    )


def _risk_band(score: int) -> str:
    if score >= 80:
        return "critical"
    if score >= 60:
        return "high"
    if score >= 30:
        return "attention"
    return "low"


def summarize_risk(
    *,
    depth: np.ndarray,
    confidence: np.ndarray,
    detections: Iterable[DetectionSummary],
    tracker: RiskTracker,
    now_ms: int,
) -> RiskSummary:
    if depth.size == 0 or confidence.size == 0 or depth.shape != confidence.shape:
        raise ValueError("depth and confidence arrays must be non-empty and have equal shape")
    if not np.isfinite(depth).all() or not np.isfinite(confidence).all():
        raise ValueError("prediction arrays must be finite")

    confidence_cutoff = float(np.percentile(confidence, 40))
    valid_mask = (depth > 0) & (confidence >= confidence_cutoff)
    values = depth[valid_mask]
    if values.size == 0:
        raise ValueError("prediction arrays contain no valid pixels")
    p10, p90 = np.percentile(values, [10, 90])
    span = max(float(p90 - p10), 1e-6)
    normalized = np.clip((depth - p10) / span, 0.0, 1.0)

    height, width = depth.shape[-2:]
    x1, x2 = int(width * 0.20), int(width * 0.80)
    y1, y2 = int(height * 0.30), height
    roi_mask = np.zeros_like(valid_mask, dtype=bool)
    roi_mask[y1:y2, x1:x2] = True
    near_fraction = float(np.mean((normalized <= 0.25)[roi_mask & valid_mask])) if np.any(roi_mask & valid_mask) else 0.0
    scene_score = float(np.clip(near_fraction / 0.50, 0.0, 1.0) * 100.0)

    enriched: list[dict] = []
    best_score = scene_score
    dominant_class = ""
    reason = "scene_proximity"
    for detection in detections:
        left, top, right, bottom = detection.bbox_norm
        px1 = max(0, min(width - 1, int(left * width)))
        py1 = max(0, min(height - 1, int(top * height)))
        px2 = max(px1 + 1, min(width, int(right * width)))
        py2 = max(py1 + 1, min(height, int(bottom * height)))
        box_mask = valid_mask[py1:py2, px1:px2]
        box_depth = normalized[py1:py2, px1:px2][box_mask]
        relative_depth = float(np.median(box_depth)) if box_depth.size else 1.0
        area = max(0.0, (right - left) * (bottom - top))
        proximity = 1.0 - relative_depth
        occupancy = float(np.clip(area / 0.25, 0.0, 1.0))
        center_distance = abs((left + right) / 2.0 - 0.5) * 2.0
        center_score = float(np.clip(1.0 - center_distance, 0.0, 1.0))
        growth = tracker.growth_score(detection.class_name, area, now_ms)
        object_score = 100.0 * (
            0.45 * proximity + 0.25 * occupancy + 0.15 * center_score + 0.15 * growth
        )
        enriched.append(
            {
                "class_name": detection.class_name,
                "score": round(float(detection.score), 4),
                "bbox_norm": [round(float(value), 5) for value in detection.bbox_norm],
                "relative_depth": round(relative_depth, 5),
                "risk_score": round(float(np.clip(object_score, 0.0, 100.0)), 2),
            }
        )
        if object_score > best_score:
            best_score = object_score
            dominant_class = detection.class_name
            reason = f"{detection.class_name}_proximity" if growth == 0 else f"{detection.class_name}_approaching"

    smoothed = int(round(tracker.smooth(best_score)))
    return RiskSummary(
        depth_p10=float(p10),
        depth_median=float(np.median(values)),
        confidence_median=float(np.median(confidence[valid_mask])),
        detections=enriched,
        risk_score=smoothed,
        risk_band=_risk_band(smoothed),
        dominant_class=dominant_class,
        reason=reason,
    )


class SsdLiteDetector:
    model_name = "SSDLite320-MobileNetV3-COCO"
    device = "cuda"

    def __init__(self, weights: Path, model_loader=None) -> None:
        import torch
        from torchvision.models.detection import SSDLite320_MobileNet_V3_Large_Weights, ssdlite320_mobilenet_v3_large

        self._torch = torch
        self._weights_enum = SSDLite320_MobileNet_V3_Large_Weights.DEFAULT
        self._preprocess = self._weights_enum.transforms()
        self._categories = self._weights_enum.meta["categories"]
        self._model = (model_loader or self._load_model)(weights, ssdlite320_mobilenet_v3_large)

    def _load_model(self, weights: Path, builder):
        model = builder(weights=None, weights_backbone=None, num_classes=len(self._categories))
        state = self._torch.load(weights, map_location="cpu", weights_only=True)
        model.load_state_dict(state)
        return model.to(self.device).eval()

    def detect_jpeg(self, image_bytes: bytes) -> list[DetectionSummary]:
        import cv2
        from PIL import Image

        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("JPEG decoding failed")
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        height, width = image.shape[:2]
        tensor = self._preprocess(Image.fromarray(image)).to(self.device)
        with self._torch.inference_mode():
            output = self._model([tensor])[0]
        detections: list[DetectionSummary] = []
        for box, label, score in zip(output["boxes"], output["labels"], output["scores"]):
            score_value = float(score.item())
            if score_value < 0.45:
                continue
            left, top, right, bottom = [float(value) for value in box.tolist()]
            class_id = int(label.item())
            detections.append(
                DetectionSummary(
                    self._categories[class_id],
                    score_value,
                    (left / width, top / height, right / width, bottom / height),
                )
            )
        return detections


class VisionAnalyzer:
    depth_model_name = "DA3-SMALL"
    detector_model_name = SsdLiteDetector.model_name

    def __init__(self, depth_engine: Da3Engine, detector: SsdLiteDetector) -> None:
        self._depth_engine = depth_engine
        self._detector = detector
        self._session_id = ""
        self._tracker = RiskTracker()

    def analyze_jpeg(self, image_bytes: bytes, *, frame_seq: int, capture_ts_ms: int, session_id: str) -> dict:
        from time import perf_counter
        from schemas import build_vision_risk_response

        if session_id != self._session_id:
            self._session_id = session_id
            self._tracker.reset()
        started = perf_counter()
        prediction = self._depth_engine.predict_jpeg(image_bytes)
        all_detections = self._detector.detect_jpeg(image_bytes)
        relevant = {"person", "bicycle", "car", "motorcycle", "bus", "truck"}
        risk_detections = [item for item in all_detections if item.class_name in relevant]
        summary = summarize_risk(
            depth=prediction.depth,
            confidence=prediction.confidence,
            detections=risk_detections,
            tracker=self._tracker,
            now_ms=capture_ts_ms,
        )
        return build_vision_risk_response(
            frame_seq=frame_seq,
            capture_ts_ms=capture_ts_ms,
            depth_p10=summary.depth_p10,
            depth_median=summary.depth_median,
            confidence_median=summary.confidence_median,
            detections=summary.detections,
            risk_score=summary.risk_score,
            risk_band=summary.risk_band,
            dominant_class=summary.dominant_class,
            reason=summary.reason,
            latency_ms=(perf_counter() - started) * 1000.0,
        )
