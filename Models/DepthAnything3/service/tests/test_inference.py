import sys
import unittest
from pathlib import Path

import numpy as np


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from inference import summarize_prediction


class PredictionSummaryTests(unittest.TestCase):
    def test_uses_depth_p10_median_and_confidence_median(self) -> None:
        depth = np.array([[[1.0, 2.0], [3.0, 4.0]]], dtype=np.float32)
        confidence = np.array([[[0.2, 0.4], [0.8, 1.0]]], dtype=np.float32)

        result = summarize_prediction(depth, confidence)

        self.assertAlmostEqual(result.depth_p10, 1.3, places=5)
        self.assertAlmostEqual(result.depth_median, 2.5, places=5)
        self.assertAlmostEqual(result.confidence_median, 0.6, places=5)

    def test_rejects_empty_prediction(self) -> None:
        with self.assertRaises(ValueError):
            summarize_prediction(np.array([], dtype=np.float32), np.array([], dtype=np.float32))
