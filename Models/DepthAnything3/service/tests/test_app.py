import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app import create_app
from inference import PredictionSummary


class FakeEngine:
    model_name = "DA3-SMALL"
    device = "cuda"

    def infer_jpeg(self, image_bytes: bytes) -> PredictionSummary:
        if image_bytes != b"\xff\xd8frame\xff\xd9":
            raise ValueError("unexpected image")
        return PredictionSummary(0.42, 1.37, 0.86)


class InferenceApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app(FakeEngine()))

    def test_infers_jpeg_and_returns_protocol_response(self) -> None:
        response = self.client.post(
            "/v1/infer",
            content=b"\xff\xd8frame\xff\xd9",
            headers={"X-Frame-Seq": "12", "X-Capture-Ts-Ms": "3456"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["type"], "vision_depth")
        self.assertEqual(payload["frame_seq"], 12)
        self.assertEqual(payload["capture_ts_ms"], 3456)
        self.assertTrue(payload["valid"])

    def test_rejects_non_jpeg_body(self) -> None:
        response = self.client.post(
            "/v1/infer",
            content=b"not-a-jpeg",
            headers={"X-Frame-Seq": "1", "X-Capture-Ts-Ms": "2"},
        )

        self.assertEqual(response.status_code, 415)
