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
    actuation_hazard_active: bool


class RiskTracker:
    """Smooth one stream and publish risk bands only after temporal confirmation."""

    _BAND_ORDER = ("low", "attention", "high", "critical")
    _BAND_LIMITS = {
        "low": (0, 29),
        "attention": (30, 59),
        "high": (60, 79),
        "critical": (80, 100),
    }

    def __init__(self) -> None:
        self._ema: float | None = None
        self._band = "low"
        self._pending_band = ""
        self._pending_count = 0

    def reset(self) -> None:
        self._ema = None
        self._band = "low"
        self._pending_band = ""
        self._pending_count = 0

    def update(self, raw_score: float, *, emergency: bool = False) -> tuple[int, str]:
        raw_score = float(np.clip(raw_score, 0.0, 100.0))
        if self._ema is None:
            self._ema = raw_score
        else:
            alpha = 0.45 if raw_score >= self._ema else 0.20
            self._ema += alpha * (raw_score - self._ema)

        if emergency:
            self._ema = max(self._ema, 80.0)
            self._band = "critical"
            self._pending_band = ""
            self._pending_count = 0
        else:
            candidate = _risk_band(int(round(self._ema)))
            if candidate == self._band:
                self._pending_band = ""
                self._pending_count = 0
            else:
                if candidate == self._pending_band:
                    self._pending_count += 1
                else:
                    self._pending_band = candidate
                    self._pending_count = 1
                current_rank = self._BAND_ORDER.index(self._band)
                candidate_rank = self._BAND_ORDER.index(candidate)
                required = 2 if candidate_rank > current_rank else 3
                if self._pending_count >= required:
                    self._band = candidate
                    self._pending_band = ""
                    self._pending_count = 0

        lower, upper = self._BAND_LIMITS[self._band]
        published_score = int(np.clip(round(self._ema), lower, upper))
        return published_score, self._band


class Da3Engine:
    model_name = "DA3-SMALL"
    device = "cuda"

    def __init__(self, weights: Path, model_loader=None, *, process_res: int = 280) -> None:
        self._weights = weights
        self._process_res = process_res
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
            process_res=self._process_res,
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
    scene_score = float(np.clip(near_fraction / 0.50, 0.0, 1.0) * 45.0)

    enriched: list[dict] = []
    best_score = scene_score
    dominant_class = ""
    reason = "scene_proximity"
    emergency = False
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
        raw_object_score = 100.0 * (
            0.40 * proximity
            + 0.25 * occupancy
            + 0.20 * center_score
            + 0.15 * float(np.clip(detection.score, 0.0, 1.0))
        )
        object_emergency = (
            raw_object_score >= 92.0
            and relative_depth <= 0.12
            and detection.score >= 0.85
            and center_score >= 0.70
        )
        object_score = raw_object_score if object_emergency else min(raw_object_score, 79.0)
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
            reason = f"{detection.class_name}_proximity"
            emergency = object_emergency

    actuation_hazard_active = (best_score >= 60.0 or emergency)
    smoothed, stable_band = tracker.update(best_score, emergency=emergency)
    return RiskSummary(
        depth_p10=float(p10),
        depth_median=float(np.median(values)),
        confidence_median=float(np.median(confidence[valid_mask])),
        detections=enriched,
        risk_score=smoothed,
        risk_band=stable_band,
        dominant_class=dominant_class,
        reason=reason,
        actuation_hazard_active=actuation_hazard_active,
    )


class Yolo26Detector:
    model_name = "YOLO26m-COCO"
    device = "cuda"
    relevant_classes = {
        "person",
        "bicycle",
        "car",
        "motorcycle",
        "bus",
        "truck",
        "traffic light",
        "stop sign",
    }

    def __init__(
        self,
        weights: Path,
        model_loader=None,
        *,
        confidence: float = 0.35,
        image_size: int = 640,
        fallback_weights: Path | None = None,
    ) -> None:
        if image_size < 320 or image_size > 1280 or image_size % 32 != 0:
            raise ValueError("YOLO image_size must be a multiple of 32 between 320 and 1280")
        self._weights = weights
        self._confidence = confidence
        self._image_size = image_size
        self._fallback_weights = fallback_weights
        self.backend = "tensorrt-fp16" if weights.suffix.lower() == ".engine" else "pytorch-cuda-fp16"
        self._model_loader = model_loader or self._load_model
        self._model = self._model_loader(weights)

    @staticmethod
    def _load_model(weights: Path):
        import torch
        from ultralytics import YOLO

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the YOLO26 service")
        if not weights.is_file():
            raise FileNotFoundError(f"YOLO26 weights not found: {weights}")
        return YOLO(str(weights), task="detect")

    @staticmethod
    def _as_array(value) -> np.ndarray:
        if hasattr(value, "detach"):
            value = value.detach()
        if hasattr(value, "cpu"):
            value = value.cpu()
        if hasattr(value, "numpy"):
            value = value.numpy()
        return np.asarray(value)

    def detect_jpeg(self, image_bytes: bytes) -> list[DetectionSummary]:
        import cv2

        image = cv2.imdecode(np.frombuffer(image_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("JPEG decoding failed")
        height, width = image.shape[:2]
        predict_args = {
            "source": image,
            "imgsz": self._image_size,
            "conf": self._confidence,
            "device": 0,
            "quantize": 16,
            "verbose": False,
        }
        try:
            results = self._model.predict(**predict_args)
        except Exception:
            if self.backend != "tensorrt-fp16" or self._fallback_weights is None:
                raise
            fallback = self._fallback_weights
            self._fallback_weights = None
            self._weights = fallback
            self._model = self._model_loader(fallback)
            self.backend = "pytorch-cuda-fp16"
            results = self._model.predict(**predict_args)
        detections: list[DetectionSummary] = []
        if not results:
            return detections
        result = results[0]
        boxes = getattr(result, "boxes", None)
        if boxes is None:
            return detections
        names = getattr(result, "names", getattr(self._model, "names", {}))
        for box, class_id, score in zip(
            self._as_array(boxes.xyxy),
            self._as_array(boxes.cls),
            self._as_array(boxes.conf),
        ):
            score_value = float(score)
            class_name = str(names[int(class_id)])
            if score_value < self._confidence or class_name not in self.relevant_classes:
                continue
            left, top, right, bottom = [float(value) for value in box]
            detections.append(
                DetectionSummary(
                    class_name,
                    score_value,
                    (
                        float(np.clip(left / width, 0.0, 1.0)),
                        float(np.clip(top / height, 0.0, 1.0)),
                        float(np.clip(right / width, 0.0, 1.0)),
                        float(np.clip(bottom / height, 0.0, 1.0)),
                    ),
                )
            )
        return detections


class VisionAnalyzer:
    depth_model_name = "DA3-SMALL"
    detector_model_name = Yolo26Detector.model_name
    device = "cuda"

    def __init__(self, depth_engine: Da3Engine, detector: Yolo26Detector) -> None:
        self._depth_engine = depth_engine
        self._detector = detector
        self._session_id = ""
        self._tracker = RiskTracker()

    @property
    def backend(self) -> str:
        return self._detector.backend

    def warmup(self, runs: int = 3) -> None:
        import cv2

        image = np.zeros((240, 320, 3), dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        if not ok:
            raise RuntimeError("failed to build warmup JPEG")
        image_bytes = encoded.tobytes()
        for _ in range(max(1, runs)):
            self._depth_engine.predict_jpeg(image_bytes)
            self._detector.detect_jpeg(image_bytes)
        self._session_id = ""
        self._tracker.reset()

    def analyze_jpeg(self, image_bytes: bytes, *, frame_seq: int, capture_ts_ms: int, session_id: str) -> dict:
        from time import perf_counter
        from schemas import build_vision_risk_response

        if session_id != self._session_id:
            self._session_id = session_id
            self._tracker.reset()
        started = perf_counter()
        prediction = self._depth_engine.predict_jpeg(image_bytes)
        all_detections = self._detector.detect_jpeg(image_bytes)
        relevant = Yolo26Detector.relevant_classes
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
            detector_model=self.detector_model_name,
            actuation_hazard_active=summary.actuation_hazard_active,
        )
