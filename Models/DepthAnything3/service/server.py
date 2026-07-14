from __future__ import annotations

import os
from pathlib import Path

from app import InferenceEngine, create_app
from inference import Da3Engine, SsdLiteDetector, VisionAnalyzer


def create_runtime_app(engine: InferenceEngine | None = None):
    token = os.environ.get("AIX_LINK_TOKEN", "")
    if engine is not None:
        return create_app(engine, token=token)

    root = os.environ.get("DA3_ROOT")
    if not root:
        raise RuntimeError("DA3_ROOT must point to the DepthAnything3 installation directory")
    root_path = Path(root)

    def load_analyzer() -> VisionAnalyzer:
        depth_engine = Da3Engine(root_path / "weights" / "DA3-SMALL")
        detector = SsdLiteDetector(
            root_path / "weights" / "SSDLite320-MobileNetV3" / "ssdlite320_mobilenet_v3_large_coco-a79551df.pth"
        )
        return VisionAnalyzer(depth_engine, detector)

    return create_app(None, token=token, analyzer_loader=load_analyzer)
