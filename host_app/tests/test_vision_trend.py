import json
import unittest

import numpy as np

from aix_host_app.vision import CameraFrame, VisionTrendAnalyzer


def make_frame(square_size: int, frame_id: int = 1) -> CameraFrame:
    data = np.zeros((90, 120, 3), dtype=np.uint8)
    if square_size > 0:
        top = (90 - square_size) // 2
        left = (120 - square_size) // 2
        data[top : top + square_size, left : left + square_size] = 255
    return CameraFrame(
        frame_id=frame_id,
        ts_ms=frame_id * 100,
        width=120,
        height=90,
        source="test",
        rgb_data=data.tobytes(),
        bytes_per_line=120 * 3,
    )


def make_shifted_square_frame(square_size: int, offset_x: int, frame_id: int) -> CameraFrame:
    data = np.zeros((90, 120, 3), dtype=np.uint8)
    top = (90 - square_size) // 2
    left = ((120 - square_size) // 2) + offset_x
    data[top : top + square_size, left : left + square_size] = 255
    return CameraFrame(
        frame_id=frame_id,
        ts_ms=frame_id * 100,
        width=120,
        height=90,
        source="test",
        rgb_data=data.tobytes(),
        bytes_per_line=120 * 3,
    )

def make_dark_object_frame(square_size: int, frame_id: int) -> CameraFrame:
    data = np.full((90, 120, 3), 180, dtype=np.uint8)
    top = (90 - square_size) // 2
    left = (120 - square_size) // 2
    data[top : top + square_size, left : left + square_size] = 35
    return CameraFrame(
        frame_id=frame_id,
        ts_ms=frame_id * 100,
        width=120,
        height=90,
        source="test",
        rgb_data=data.tobytes(),
        bytes_per_line=120 * 3,
    )

class VisionTrendAnalyzerTests(unittest.TestCase):
    def test_static_frames_keep_looming_low(self):
        analyzer = VisionTrendAnalyzer()

        analyzer.analyze(make_frame(20, frame_id=1))
        result = analyzer.analyze(make_frame(20, frame_id=2))

        self.assertLess(result.features.looming, 0.2)
        self.assertLess(result.risk_level, 20)

    def test_growing_center_object_raises_looming(self):
        analyzer = VisionTrendAnalyzer()

        analyzer.analyze(make_frame(8, frame_id=1))
        analyzer.analyze(make_frame(24, frame_id=2))
        result = analyzer.analyze(make_frame(48, frame_id=3))

        self.assertGreater(result.features.looming, 0.5)
        self.assertGreaterEqual(result.risk_level, 50)
        self.assertTrue(result.features.valid)
    def test_center_growth_scores_higher_than_lateral_shift(self):
        growth = VisionTrendAnalyzer()
        growth.analyze(make_frame(12, frame_id=1))
        growth_result = growth.analyze(make_frame(44, frame_id=2))

        lateral = VisionTrendAnalyzer()
        lateral.analyze(make_shifted_square_frame(28, offset_x=-18, frame_id=1))
        lateral_result = lateral.analyze(make_shifted_square_frame(28, offset_x=18, frame_id=2))

        self.assertGreater(growth_result.features.looming, 0.35)
        self.assertLess(lateral_result.features.looming, growth_result.features.looming)
    def test_dark_center_object_growth_raises_looming(self):
        analyzer = VisionTrendAnalyzer()

        analyzer.analyze(make_dark_object_frame(12, frame_id=1))
        result = analyzer.analyze(make_dark_object_frame(46, frame_id=2))

        self.assertGreater(result.features.looming, 0.35)
        self.assertGreaterEqual(result.risk_level, 20)

    def test_feature_event_serializes_to_vision_ndjson(self):
        analyzer = VisionTrendAnalyzer()
        result = analyzer.analyze(make_frame(24, frame_id=7))

        payload = json.loads(result.features.to_json_line(seq=3))

        self.assertEqual(payload["type"], "vision")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["seq"], 3)
        self.assertEqual(payload["source"], "pc_camera")
        self.assertIn("looming", payload)
        self.assertIn("area_rate", payload)
        self.assertIn("center_motion", payload)
        self.assertIn("confidence", payload)


if __name__ == "__main__":
    unittest.main()
