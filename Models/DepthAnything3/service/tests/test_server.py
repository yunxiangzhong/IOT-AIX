import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from server import create_runtime_app
from inference import PredictionSummary


class FakeEngine:
    model_name = "DA3-SMALL"
    device = "cuda"

    def infer_jpeg(self, image_bytes: bytes) -> PredictionSummary:
        return PredictionSummary(0.1, 0.2, 0.3)


class ServerBootstrapTests(unittest.TestCase):
    def test_builds_health_endpoint_with_injected_engine(self) -> None:
        client = TestClient(create_runtime_app(engine=FakeEngine()))

        response = client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["model"], "DA3-SMALL")
