import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app import create_app


class FakeAnalyzer:
    def analyze_jpeg(self, image_bytes: bytes, *, frame_seq: int, capture_ts_ms: int, session_id: str) -> dict:
        self.last = (image_bytes, frame_seq, capture_ts_ms, session_id)
        return {
            "type": "vision_risk",
            "version": 1,
            "frame_seq": frame_seq,
            "capture_ts_ms": capture_ts_ms,
            "models": {"depth": "DA3-SMALL", "detector": "SSDLite320-MobileNetV3-COCO"},
            "depth_kind": "relative",
            "depth_p10": 0.2,
            "depth_median": 0.7,
            "confidence_median": 0.9,
            "detections": [],
            "risk_score": 42,
            "risk_band": "attention",
            "dominant_class": "",
            "reason": "scene_proximity",
            "latency_ms": 12.0,
            "valid": True,
        }


class AnalyzeApiTests(unittest.TestCase):
    def test_analyze_returns_risk_response_and_stream_headers(self) -> None:
        analyzer = FakeAnalyzer()
        client = TestClient(create_app(None, analyzer=analyzer))

        response = client.post(
            "/v1/analyze",
            content=b"\xff\xd8frame\xff\xd9",
            headers={
                "X-Frame-Seq": "12",
                "X-Capture-Ts-Ms": "3456",
                "X-Session-Id": "session-1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["type"], "vision_risk")
        self.assertEqual(response.json()["risk_score"], 42)
        self.assertEqual(analyzer.last[3], "session-1")

    def test_analyze_rejects_missing_session_header(self) -> None:
        client = TestClient(create_app(None, analyzer=FakeAnalyzer()))

        response = client.post(
            "/v1/analyze",
            content=b"\xff\xd8frame\xff\xd9",
            headers={"X-Frame-Seq": "1", "X-Capture-Ts-Ms": "2"},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
