from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class PredictionSummary:
    depth_p10: float
    depth_median: float
    confidence_median: float


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
        return summarize_prediction(prediction.depth, prediction.conf)


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
