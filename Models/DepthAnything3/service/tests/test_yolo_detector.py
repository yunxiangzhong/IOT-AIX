import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from inference import Yolo26Detector


class FakeYoloModel:
    def __init__(self) -> None:
        self.calls = []

    def predict(self, **kwargs):
        self.calls.append(kwargs)
        return [
            SimpleNamespace(
                names={2: "car", 9: "traffic light", 11: "stop sign", 15: "cat"},
                boxes=SimpleNamespace(
                    xyxy=np.array(
                        [
                            [20.0, 10.0, 120.0, 80.0],
                            [0.0, 0.0, 30.0, 30.0],
                            [150.0, 20.0, 199.0, 90.0],
                            [30.0, 30.0, 60.0, 60.0],
                        ]
                    ),
                    cls=np.array([2, 15, 11, 9]),
                    conf=np.array([0.91, 0.99, 0.80, 0.20]),
                ),
            )
        ]


class Yolo26DetectorTests(unittest.TestCase):
    def test_filters_traffic_classes_and_normalizes_boxes(self) -> None:
        image = np.full((100, 200, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        model = FakeYoloModel()
        detector = Yolo26Detector(Path("yolo26m.pt"), model_loader=lambda _: model)

        detections = detector.detect_jpeg(encoded.tobytes())

        self.assertEqual([item.class_name for item in detections], ["car", "stop sign"])
        self.assertEqual(detections[0].bbox_norm, (0.1, 0.1, 0.6, 0.8))
        self.assertEqual(detections[1].bbox_norm, (0.75, 0.2, 0.995, 0.9))
        self.assertEqual(model.calls[0]["device"], 0)
        self.assertEqual(model.calls[0]["quantize"], 16)
        self.assertNotIn("half", model.calls[0])
        self.assertEqual(model.calls[0]["imgsz"], 640)

    def test_rejects_unreadable_jpeg(self) -> None:
        detector = Yolo26Detector(Path("yolo26m.pt"), model_loader=lambda _: FakeYoloModel())

        with self.assertRaises(ValueError):
            detector.detect_jpeg(b"broken")

    def test_allows_camera_matched_inference_size(self) -> None:
        image = np.full((100, 200, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        model = FakeYoloModel()
        detector = Yolo26Detector(
            Path("yolo26m.pt"),
            model_loader=lambda _: model,
            image_size=512,
        )

        detector.detect_jpeg(encoded.tobytes())

        self.assertEqual(model.calls[0]["imgsz"], 512)

    def test_engine_failure_falls_back_to_cuda_pt(self) -> None:
        image = np.full((100, 200, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        good_model = FakeYoloModel()

        class BrokenEngine:
            def predict(self, **kwargs):
                raise RuntimeError("incompatible TensorRT engine")

        loaded = []

        def loader(path):
            loaded.append(path)
            return BrokenEngine() if path.suffix == ".engine" else good_model

        detector = Yolo26Detector(
            Path("yolo26m.engine"),
            model_loader=loader,
            fallback_weights=Path("yolo26m.pt"),
        )

        detections = detector.detect_jpeg(encoded.tobytes())

        self.assertTrue(detections)
        self.assertEqual(loaded, [Path("yolo26m.engine"), Path("yolo26m.pt")])
        self.assertEqual(detector.backend, "pytorch-cuda-fp16")


if __name__ == "__main__":
    unittest.main()
