import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from inference import Da3Engine


class FakeModel:
    def __init__(self) -> None:
        self.calls = []

    def inference(self, images, **kwargs):
        self.calls.append((images, kwargs))
        return SimpleNamespace(
            depth=np.array([[[1.0, 2.0], [3.0, 4.0]]], dtype=np.float32),
            conf=np.array([[[0.2, 0.4], [0.8, 1.0]]], dtype=np.float32),
        )


class Da3EngineTests(unittest.TestCase):
    def test_decodes_jpeg_and_runs_model_at_online_resolution(self) -> None:
        image = np.full((8, 8, 3), 127, dtype=np.uint8)
        ok, encoded = cv2.imencode(".jpg", image)
        self.assertTrue(ok)
        model = FakeModel()
        engine = Da3Engine(Path("weights"), model_loader=lambda _: model)

        summary = engine.infer_jpeg(encoded.tobytes())

        self.assertAlmostEqual(summary.depth_p10, 1.3, places=5)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(model.calls[0][1]["process_res"], 280)

    def test_rejects_unreadable_jpeg(self) -> None:
        engine = Da3Engine(Path("weights"), model_loader=lambda _: FakeModel())

        with self.assertRaises(ValueError):
            engine.infer_jpeg(b"\xff\xd8broken\xff\xd9")
