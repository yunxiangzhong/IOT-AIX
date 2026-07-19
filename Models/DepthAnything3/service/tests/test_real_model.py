import math
import subprocess
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np


SERVICE_ROOT = Path(__file__).resolve().parents[1]
MODEL_ROOT = SERVICE_ROOT.parent
PROJECT_ROOT = MODEL_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from inference import Da3Engine


def shared_weights() -> Path:
    common_git_dir = subprocess.run(
        ["git", "-C", str(PROJECT_ROOT), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()
    return Path(common_git_dir).parent / "Models" / "DepthAnything3" / "weights" / "DA3-SMALL"


class RealDa3ModelTests(unittest.TestCase):
    def test_runs_cuda_inference_from_local_weights(self) -> None:
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        image[:, :160] = (30, 80, 160)
        image[:, 160:] = (160, 80, 30)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)

        summary = Da3Engine(shared_weights()).infer_jpeg(encoded.tobytes())

        self.assertTrue(math.isfinite(summary.depth_p10))
        self.assertTrue(math.isfinite(summary.depth_median))
        self.assertTrue(math.isfinite(summary.confidence_median))
