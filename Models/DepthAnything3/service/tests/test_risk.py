import sys
import unittest
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from inference import DetectionSummary, RiskTracker, summarize_risk


class RiskAlgorithmTests(unittest.TestCase):
    def test_scene_risk_reaches_100_when_half_forward_roi_is_near(self) -> None:
        depth = np.ones((100, 100), dtype=np.float32)
        depth[50:, 20:70] = 0.1
        confidence = np.ones_like(depth)

        result = summarize_risk(
            depth=depth,
            confidence=confidence,
            detections=[],
            tracker=RiskTracker(),
            now_ms=1000,
        )

        self.assertEqual(result.risk_score, 100)
        self.assertEqual(result.risk_band, "critical")
        self.assertEqual(result.dominant_class, "")

    def test_relevant_detection_contributes_to_risk_and_is_reported(self) -> None:
        depth = np.full((100, 100), 0.9, dtype=np.float32)
        depth[30:80, 40:60] = 0.2
        confidence = np.ones_like(depth)
        detections = [
            DetectionSummary("car", 0.9, (0.4, 0.3, 0.6, 0.8), 0.2),
        ]

        result = summarize_risk(
            depth=depth,
            confidence=confidence,
            detections=detections,
            tracker=RiskTracker(),
            now_ms=1000,
        )

        self.assertGreater(result.risk_score, 0)
        self.assertEqual(result.dominant_class, "car")
        self.assertEqual(result.risk_band, "high")

    def test_smoothing_rises_faster_than_it_falls(self) -> None:
        tracker = RiskTracker()
        first = tracker.smooth(100)
        falling = tracker.smooth(0)

        self.assertEqual(first, 100)
        self.assertAlmostEqual(falling, 75.0)


if __name__ == "__main__":
    unittest.main()
