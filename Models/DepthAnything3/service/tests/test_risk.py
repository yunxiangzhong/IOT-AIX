import sys
import unittest
from pathlib import Path

import numpy as np

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from inference import DetectionSummary, RiskTracker, summarize_risk


class RiskAlgorithmTests(unittest.TestCase):
    def test_scene_only_risk_is_capped_at_attention(self) -> None:
        depth = np.ones((100, 100), dtype=np.float32)
        depth[50:, 20:70] = 0.1
        confidence = np.ones_like(depth)
        tracker = RiskTracker()

        result = None
        for now_ms in (1000, 2000):
            result = summarize_risk(
                depth=depth,
                confidence=confidence,
                detections=[],
                tracker=tracker,
                now_ms=now_ms,
            )

        self.assertIsNotNone(result)
        self.assertLessEqual(result.risk_score, 59)
        self.assertEqual(result.risk_band, "attention")
        self.assertEqual(result.dominant_class, "")

    def test_relevant_detection_contributes_to_risk_and_is_reported(self) -> None:
        depth = np.full((100, 100), 0.9, dtype=np.float32)
        depth[30:80, 40:60] = 0.2
        confidence = np.ones_like(depth)
        detections = [
            DetectionSummary("car", 0.9, (0.4, 0.3, 0.6, 0.8), 0.2),
        ]

        tracker = RiskTracker()
        result = None
        for now_ms in (1000, 2000):
            result = summarize_risk(
                depth=depth,
                confidence=confidence,
                detections=detections,
                tracker=tracker,
                now_ms=now_ms,
            )

        self.assertIsNotNone(result)
        self.assertGreater(result.risk_score, 0)
        self.assertEqual(result.dominant_class, "car")
        self.assertEqual(result.risk_band, "high")

    def test_same_class_objects_do_not_create_growth_spike(self) -> None:
        depth = np.full((100, 100), 0.9, dtype=np.float32)
        depth[30:70, 10:30] = 0.4
        depth[30:70, 70:90] = 0.4
        confidence = np.ones_like(depth)
        tracker = RiskTracker()

        first = summarize_risk(
            depth=depth,
            confidence=confidence,
            detections=[
                DetectionSummary("car", 0.9, (0.1, 0.3, 0.3, 0.7)),
                DetectionSummary("car", 0.9, (0.7, 0.3, 0.9, 0.7)),
            ],
            tracker=tracker,
            now_ms=1000,
        )

        self.assertNotIn("approaching", first.reason)
        self.assertTrue(all(item["risk_score"] < 80 for item in first.detections))

    def test_single_spike_does_not_jump_to_high_or_critical(self) -> None:
        tracker = RiskTracker()

        score, band = tracker.update(95)

        self.assertLess(score, 60)
        self.assertIn(band, {"low", "attention"})

    def test_two_frames_escalate_and_three_frames_deescalate(self) -> None:
        tracker = RiskTracker()

        self.assertEqual(tracker.update(70)[1], "low")
        score, band = tracker.update(70)
        self.assertEqual(band, "high")
        self.assertGreaterEqual(score, 60)

        self.assertEqual(tracker.update(10)[1], "high")
        self.assertEqual(tracker.update(10)[1], "high")
        score, band = tracker.update(10)
        self.assertEqual(band, "attention")
        self.assertTrue(30 <= score <= 59)

    def test_emergency_can_escalate_immediately(self) -> None:
        score, band = RiskTracker().update(94, emergency=True)

        self.assertEqual(band, "critical")
        self.assertGreaterEqual(score, 80)

    def test_actuation_hazard_active_true_when_raw_score_above_threshold(self) -> None:
        """actuation_hazard_active reflects unsmoothed raw risk, not smoothed."""
        depth = np.full((100, 100), 0.9, dtype=np.float32)
        depth[30:80, 40:60] = 0.2
        confidence = np.ones_like(depth)
        detections = [
            DetectionSummary("car", 0.9, (0.4, 0.3, 0.6, 0.8), 0.2),
        ]
        tracker = RiskTracker()
        result = None
        for now_ms in (1000, 2000):
            result = summarize_risk(
                depth=depth, confidence=confidence,
                detections=detections, tracker=tracker, now_ms=now_ms,
            )
        self.assertIsNotNone(result)
        self.assertTrue(result.actuation_hazard_active,
                        "raw object score >= 60 should set actuation_hazard_active=True")

    def test_actuation_hazard_active_false_for_low_raw_score(self) -> None:
        """Low raw risk must produce actuation_hazard_active=False regardless of EMA."""
        depth = np.ones((100, 100), dtype=np.float32)
        depth[50:, 20:70] = 0.1
        confidence = np.ones_like(depth)
        tracker = RiskTracker()

        # Saturate the EMA so smoothed stays high.
        for _ in range(6):
            tracker.update(50.0)
        # Single frame with low raw risk: unsmoothed hazard should be false.
        result = summarize_risk(
            depth=depth, confidence=confidence, detections=[],
            tracker=tracker, now_ms=8000,
        )
        self.assertFalse(result.actuation_hazard_active,
                         "low raw score (<60) should set actuation_hazard_active=False")

    def test_actuation_hazard_active_with_emergency(self) -> None:
        """Emergency must force actuation_hazard_active=True."""
        depth = np.full((100, 100), 0.5, dtype=np.float32)
        depth[40:80, 30:70] = 0.05
        confidence = np.ones_like(depth)
        detections = [
            DetectionSummary("car", 0.92, (0.35, 0.45, 0.65, 0.75), 0.08),
        ]
        tracker = RiskTracker()
        result = None
        for now_ms in (1000, 2000):
            result = summarize_risk(
                depth=depth, confidence=confidence,
                detections=detections, tracker=tracker, now_ms=now_ms,
            )
        self.assertIsNotNone(result)
        self.assertTrue(result.actuation_hazard_active,
                        "emergency-qualifying detection must set actuation_hazard_active=True")


if __name__ == "__main__":
    unittest.main()
