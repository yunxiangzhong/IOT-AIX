import sys
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app import create_app
from frame_pipeline import FrameEnvelope, LatestFrameStore, RiskCallbackClient


JPEG_A = b"\xff\xd8frame-a\xff\xd9"
JPEG_B = b"\xff\xd8frame-b\xff\xd9"


def frame(seq: int, body: bytes = JPEG_A) -> FrameEnvelope:
    return FrameEnvelope(
        device_id="aix-helmet-01",
        boot_id="0123456789abcdef",
        frame_seq=seq,
        capture_ts_ms=seq * 400,
        source_ip="192.168.137.20",
        jpeg=body,
        received_ts_ms=10_000 + seq,
    )


class LatestFrameStoreTests(unittest.TestCase):
    def test_replaces_pending_frame_but_keeps_latest_for_ui(self) -> None:
        store = LatestFrameStore()

        self.assertFalse(store.put(frame(1)))
        self.assertTrue(store.put(frame(2, JPEG_B)))

        pending = store.take(timeout=0)
        self.assertIsNotNone(pending)
        self.assertEqual(pending.frame_seq, 2)
        self.assertEqual(store.latest("aix-helmet-01").jpeg, JPEG_B)


class FrameApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(None, token="unit-secret", start_worker=False)
        self.client = TestClient(self.app)
        self.headers = {
            "X-AIX-Token": "unit-secret",
            "X-Device-Id": "aix-helmet-01",
            "X-Boot-Id": "0123456789abcdef",
            "X-Frame-Seq": "12",
            "X-Capture-Ts-Ms": "4800",
        }

    def test_accepts_jpeg_immediately_while_model_is_loading(self) -> None:
        response = self.client.post("/v1/frames", content=JPEG_A, headers=self.headers)

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["type"], "frame_ack")
        self.assertEqual(payload["frame_seq"], 12)
        self.assertEqual(payload["model_state"], "loading")
        self.assertTrue(payload["accepted"])

    def test_rejects_bad_token_and_oversized_or_non_jpeg_body(self) -> None:
        bad_headers = dict(self.headers, **{"X-AIX-Token": "wrong"})
        self.assertEqual(self.client.post("/v1/frames", content=JPEG_A, headers=bad_headers).status_code, 401)
        self.assertEqual(self.client.post("/v1/frames", content=b"text", headers=self.headers).status_code, 415)
        oversized = b"\xff\xd8" + (b"x" * (256 * 1024)) + b"\xff\xd9"
        self.assertEqual(self.client.post("/v1/frames", content=oversized, headers=self.headers).status_code, 413)

    def test_exposes_latest_frame_and_unified_chain_state(self) -> None:
        self.client.post("/v1/frames", content=JPEG_A, headers=self.headers)

        frame_response = self.client.get("/v1/frame/latest.jpg?device_id=aix-helmet-01")
        state_response = self.client.get("/v1/state/latest?device_id=aix-helmet-01")

        self.assertEqual(frame_response.status_code, 200)
        self.assertEqual(frame_response.content, JPEG_A)
        self.assertEqual(frame_response.headers["x-frame-seq"], "12")
        self.assertEqual(frame_response.headers["x-boot-id"], "0123456789abcdef")
        self.assertEqual(state_response.status_code, 200)
        state = state_response.json()
        self.assertEqual(state["type"], "chain_state")
        self.assertEqual(state["upload"]["last_frame_seq"], 12)
        self.assertEqual(state["model"]["state"], "loading")


class RiskCallbackTests(unittest.TestCase):
    def test_retries_then_requires_matching_action_ack(self) -> None:
        attempts = []
        expected_frame = frame(9)

        def transport(url, token, payload, timeout_s):
            attempts.append((url, token, payload["frame_seq"]))
            if len(attempts) < 3:
                raise OSError("temporary")
            return {
                "type": "action_ack",
                "version": 1,
                "frame_seq": 9,
                "accepted": True,
                "stale": False,
                "action_state": "attention",
                "rgb_pattern": "yellow_blink_1hz",
            }

        client = RiskCallbackClient(
            token="unit-secret",
            transport=transport,
            retry_delays_s=(0, 0, 0),
        )
        ack = client.send(expected_frame, {"frame_seq": 9}, is_current=lambda: True)

        self.assertEqual(len(attempts), 3)
        self.assertEqual(attempts[0][0], "http://192.168.137.20:8080/risk")
        self.assertEqual(ack["rgb_pattern"], "yellow_blink_1hz")

    def test_drops_retry_when_result_has_been_superseded(self) -> None:
        attempts = []

        def transport(url, token, payload, timeout_s):
            attempts.append(payload["frame_seq"])
            raise OSError("temporary")

        current = iter((True, False))
        client = RiskCallbackClient(token="secret", transport=transport, retry_delays_s=(0, 0.2, 0.2))
        ack = client.send(frame(4), {"frame_seq": 4}, is_current=lambda: next(current, False))

        self.assertIsNone(ack)
        self.assertEqual(attempts, [4])


class AsyncPipelineTests(unittest.TestCase):
    def test_accepts_during_load_then_analyzes_latest_and_records_action_ack(self) -> None:
        release_loader = threading.Event()

        class Analyzer:
            depth_model_name = "DA3-SMALL"
            device = "cuda"

            def analyze_jpeg(self, image_bytes, *, frame_seq, capture_ts_ms, session_id):
                return {
                    "type": "vision_risk", "version": 1,
                    "frame_seq": frame_seq, "capture_ts_ms": capture_ts_ms,
                    "risk_score": 44, "risk_band": "attention",
                    "dominant_class": "", "reason": "scene_proximity",
                    "latency_ms": 12.0, "valid": True,
                }

        def loader():
            release_loader.wait(1.0)
            return Analyzer()

        def transport(url, token, payload, timeout_s):
            return {
                "type": "action_ack", "version": 1, "frame_seq": payload["frame_seq"],
                "accepted": True, "stale": False, "action_state": "attention",
                "rgb_pattern": "yellow_blink_1hz",
            }

        callback = RiskCallbackClient(token="secret", transport=transport, retry_delays_s=(0,))
        app = create_app(None, token="secret", analyzer_loader=loader, callback_client=callback)
        with TestClient(app) as client:
            response = client.post(
                "/v1/frames", content=JPEG_A,
                headers={
                    "X-AIX-Token": "secret", "X-Device-Id": "aix-helmet-01",
                    "X-Boot-Id": "0123456789abcdef", "X-Frame-Seq": "21",
                    "X-Capture-Ts-Ms": "8400",
                },
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json()["model_state"], "loading")
            release_loader.set()
            deadline = time.monotonic() + 1.5
            state = {}
            while time.monotonic() < deadline:
                state = client.get("/v1/state/latest?device_id=aix-helmet-01").json()
                if state["action"]["confirmed"]:
                    break
                time.sleep(0.02)

            self.assertEqual(state["model"]["state"], "ready")
            self.assertEqual(state["risk"]["score"], 44)
            self.assertEqual(state["action"]["frame_seq"], 21)
            self.assertEqual(state["action"]["rgb_pattern"], "yellow_blink_1hz")


if __name__ == "__main__":
    unittest.main()
