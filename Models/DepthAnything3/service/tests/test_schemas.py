import math
import sys
import unittest
from pathlib import Path


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from schemas import build_vision_depth_response


class VisionDepthSchemaTests(unittest.TestCase):
    def test_builds_relative_depth_response(self) -> None:
        response = build_vision_depth_response(
            frame_seq=12,
            capture_ts_ms=3456,
            depth_p10=0.42,
            depth_median=1.37,
            confidence_median=0.86,
            latency_ms=74.5,
        )

        self.assertEqual(response["type"], "vision_depth")
        self.assertEqual(response["version"], 1)
        self.assertEqual(response["frame_seq"], 12)
        self.assertEqual(response["depth_kind"], "relative")
        self.assertTrue(response["valid"])

    def test_rejects_non_finite_measurements(self) -> None:
        with self.assertRaises(ValueError):
            build_vision_depth_response(
                frame_seq=1,
                capture_ts_ms=2,
                depth_p10=math.nan,
                depth_median=1.0,
                confidence_median=0.8,
                latency_ms=5.0,
            )
