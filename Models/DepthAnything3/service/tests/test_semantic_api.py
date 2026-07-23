from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app import create_app
from frame_pipeline import FrameEnvelope
from semantic_gateway import SemanticGatewayClient


JPEG = b"\xff\xd8semantic-frame\xff\xd9"


class SemanticApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.device_calls: list[tuple] = []

        def device_transport(url, token, payload, timeout_s):
            self.device_calls.append((url, token, payload, timeout_s))
            return {
                "accepted": True,
                "flashed": True,
                "suppressed": False,
                "effective_rgb_pattern": "cyan_result_pulse",
            }

        result = {
            "scene_type": "road",
            "summary": "道路畅通",
            "road_environment": "normal",
            "traffic_flow": "smooth",
            "visibility": "clear",
            "changes": [],
            "confidence": 0.91,
            "uncertainty": "",
        }
        semantic_client = SemanticGatewayClient(
            api_key="sk-test",
            completion=lambda _request: json.dumps(result),
        )
        self.app = create_app(
            None,
            token="unit-secret",
            semantic_client=semantic_client,
            device_transport=device_transport,
            start_worker=False,
        )
        self.client = TestClient(self.app)
        self.frame = FrameEnvelope(
            device_id="aix-helmet-01",
            boot_id="0123456789abcdef",
            frame_seq=3,
            capture_ts_ms=7000,
            received_ts_ms=7020,
            source_ip="192.168.137.20",
            jpeg=JPEG,
        )

    def test_keyframe_route_only_reads_valid_cached_id_and_index(self) -> None:
        cache = self.app.state.semantic_cache
        cache.put("sem-valid", {"status": "ready"}, (self.frame,) * 3)

        response = self.client.get("/v1/semantic/sem-valid/keyframes/2.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, JPEG)
        self.assertEqual(
            self.client.get("/v1/semantic/not-present/keyframes/1.jpg").status_code,
            404,
        )
        self.assertEqual(
            self.client.get("/v1/semantic/sem-valid/keyframes/4.jpg").status_code,
            422,
        )

    def test_collision_ack_is_proxied_using_latest_real_device_identity(self) -> None:
        store = self.app.state.frame_store
        store.put(self.frame)

        response = self.client.post(
            "/v1/collision-indicator/ack",
            headers={"X-AIX-Token": "unit-secret"},
            json={
                "device_id": self.frame.device_id,
                "boot_id": self.frame.boot_id,
                "impact_count": 4,
            },
        )

        self.assertEqual(response.status_code, 200)
        url, token, payload, _timeout = self.device_calls[-1]
        self.assertTrue(url.endswith("/collision-indicator/ack"))
        self.assertEqual(token, "unit-secret")
        self.assertEqual(payload["boot_id"], self.frame.boot_id)
        self.assertEqual(payload["impact_count"], 4)

    def test_collision_ack_rejects_stale_identity(self) -> None:
        self.app.state.frame_store.put(self.frame)
        response = self.client.post(
            "/v1/collision-indicator/ack",
            headers={"X-AIX-Token": "unit-secret"},
            json={
                "device_id": self.frame.device_id,
                "boot_id": "fedcba9876543210",
                "impact_count": 4,
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.device_calls, [])


if __name__ == "__main__":
    unittest.main()
