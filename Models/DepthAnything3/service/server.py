from __future__ import annotations

import os
from pathlib import Path

from app import InferenceEngine, create_app
from inference import Da3Engine


def create_runtime_app(engine: InferenceEngine | None = None):
    if engine is None:
        root = os.environ.get("DA3_ROOT")
        if not root:
            raise RuntimeError("DA3_ROOT must point to the DepthAnything3 installation directory")
        engine = Da3Engine(Path(root) / "weights" / "DA3-SMALL")
    return create_app(engine)
