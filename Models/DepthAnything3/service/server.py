from __future__ import annotations

import os
from pathlib import Path

from app import InferenceEngine, create_app
from inference import Da3Engine, VisionAnalyzer, Yolo26Detector


def create_runtime_app(engine: InferenceEngine | None = None):
    token = os.environ.get("AIX_LINK_TOKEN", "")
    if engine is not None:
        return create_app(engine, token=token)

    root = os.environ.get("DA3_ROOT")
    if not root:
        raise RuntimeError("DA3_ROOT must point to the DepthAnything3 installation directory")
    root_path = Path(root)

    def load_analyzer() -> VisionAnalyzer:
        depth_engine = Da3Engine(root_path / "weights" / "DA3-SMALL", process_res=280)
        detector_root = root_path / "weights" / "YOLO26m"
        engine_path = detector_root / "yolo26m.engine"
        pt_path = detector_root / "yolo26m.pt"
        detector = Yolo26Detector(
            engine_path if engine_path.is_file() else pt_path,
            image_size=512,
            fallback_weights=pt_path if engine_path.is_file() else None,
        )
        return VisionAnalyzer(depth_engine, detector)

    return create_app(None, token=token, analyzer_loader=load_analyzer)
