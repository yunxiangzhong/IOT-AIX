from __future__ import annotations

import os
from pathlib import Path

from app import InferenceEngine, create_app
from inference import Da3Engine, SsdLiteDetector, VisionAnalyzer


def create_runtime_app(engine: InferenceEngine | None = None):
    if engine is None:
        root = os.environ.get("DA3_ROOT")
        if not root:
            raise RuntimeError("DA3_ROOT must point to the DepthAnything3 installation directory")
        engine = Da3Engine(Path(root) / "weights" / "DA3-SMALL")
        detector = SsdLiteDetector(Path(root) / "weights" / "SSDLite320-MobileNetV3" / "ssdlite320_mobilenet_v3_large_coco-a79551df.pth")
        return create_app(engine, analyzer=VisionAnalyzer(engine, detector))
    return create_app(engine)
