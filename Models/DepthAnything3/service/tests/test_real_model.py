import math
import sys
import unittest
from pathlib import Path

import cv2
import numpy as np


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from inference import Da3Engine


WEIGHTS = SERVICE_ROOT.parent / "weights" / "DA3-SMALL"


class RealDa3ModelTests(unittest.TestCase):
    def test_runs_cuda_inference_from_local_weights(self) -> None:
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        image[:, :160] = (30, 80, 160)
        image[:, 160:] = (160, 80, 30)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)

        summary = Da3Engine(WEIGHTS).infer_jpeg(encoded.tobytes())

        self.assertTrue(math.isfinite(summary.depth_p10))
        self.assertTrue(math.isfinite(summary.depth_median))
        self.assertTrue(math.isfinite(summary.confidence_median))
