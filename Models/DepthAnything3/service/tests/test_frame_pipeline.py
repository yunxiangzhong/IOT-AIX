import sys
import threading
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from app import create_app
from frame_pipeline import FrameEnvelope, LatestFrameStore, RiskCallbackClient, VoicePromptPolicy


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

    def test_requires_voice_ack_when_a_voice_prompt_was_sent(self) -> None:
        def transport(url, token, payload, timeout_s):
            return {
                "type": "action_ack", "version": 1, "frame_seq": payload["frame_seq"],
                "accepted": True, "stale": False, "action_state": "high",
                "rgb_pattern": "orange_blink_2hz",
            }

        client = RiskCallbackClient(token="secret", transport=transport, retry_delays_s=(0,))
        self.assertIsNone(client.send(
            frame(8),
            {"frame_seq": 8, "voice_prompt": {"command_id": "boot:8:2", "track": 2}},
            is_current=lambda: True,
        ))

    def test_rejects_invalid_e2e_latency_even_when_voice_ack_is_present(self) -> None:
        def transport(url, token, payload, timeout_s):
            return {
                "type": "action_ack", "version": 1, "frame_seq": payload["frame_seq"],
                "accepted": True, "stale": False, "action_state": "high",
                "rgb_pattern": "orange_blink_2hz", "e2e_latency_ms": -1,
                "voice_ack": {
                    "requested": True, "command_id": "boot:8:2", "track": 2,
                    "accepted": True, "duplicate": False, "status": "queued",
                },
            }

        client = RiskCallbackClient(token="secret", transport=transport, retry_delays_s=(0,))
        self.assertIsNone(client.send(
            frame(8),
            {"frame_seq": 8, "voice_prompt": {"command_id": "boot:8:2", "track": 2}},
            is_current=lambda: True,
        ))
        self.assertIn("e2e_latency_ms", client.last_error)

    def test_rejects_voice_ack_that_does_not_strictly_match_prompt(self) -> None:
        prompt = {"command_id": "boot:8:2", "track": 2}
        baseline = {
            "requested": True, "command_id": prompt["command_id"], "track": prompt["track"],
            "accepted": True, "duplicate": False, "status": "queued",
        }
        invalid_cases = (
            {"requested": False},
            {"command_id": "other:8:2"},
            {"track": 3},
            {"accepted": "true"},
            {"duplicate": "false"},
            {"status": "unknown"},
            {"accepted": False},
            {"status": "suppressed", "accepted": True},
            {"status": "duplicate", "duplicate": False},
        )

        for overrides in invalid_cases:
            with self.subTest(overrides=overrides):
                def transport(url, token, payload, timeout_s):
                    voice_ack = dict(baseline)
                    voice_ack.update(overrides)
                    return {
                        "type": "action_ack", "version": 1, "frame_seq": payload["frame_seq"],
                        "accepted": True, "stale": False, "action_state": "high",
                        "rgb_pattern": "orange_blink_2hz", "voice_ack": voice_ack,
                    }

                client = RiskCallbackClient(token="secret", transport=transport, retry_delays_s=(0,))
                self.assertIsNone(client.send(frame(8), {"frame_seq": 8, "voice_prompt": prompt}, is_current=lambda: True))
                self.assertIn("voice_ack", client.last_error)

    def test_retries_keep_the_same_voice_command_id_and_accept_cached_voice_ack(self) -> None:
        sent_prompts = []

        def transport(_url, _token, payload, _timeout_s):
            sent_prompts.append(payload["voice_prompt"])
            if len(sent_prompts) == 1:
                raise OSError("temporary")
            return {
                "type": "action_ack", "version": 1, "frame_seq": payload["frame_seq"],
                "accepted": True, "stale": False, "action_state": "high",
                "rgb_pattern": "orange_blink_2hz",
                "voice_ack": {
                    "requested": True, "command_id": payload["voice_prompt"]["command_id"],
                    "track": payload["voice_prompt"]["track"], "accepted": True,
                    "duplicate": True, "status": "duplicate",
                },
            }

        client = RiskCallbackClient(token="secret", transport=transport, retry_delays_s=(0, 0))
        prompt = {"command_id": "0123456789abcdef:8:2", "track": 2}
        ack = client.send(frame(8), {"frame_seq": 8, "voice_prompt": prompt}, is_current=lambda: True)

        self.assertEqual(sent_prompts, [prompt, prompt])
        self.assertTrue(ack["voice_ack"]["duplicate"])


class VoicePromptPolicyTests(unittest.TestCase):
    def test_emits_on_entry_upgrade_and_same_band_cooldown(self) -> None:
        policy = VoicePromptPolicy(repeat_interval_ms=10_000)
        current = frame(20)

        attention = policy.enrich(current, {"risk_band": "attention"}, now_ms=1_000)
        self.assertEqual(attention["voice_prompt"], {"command_id": "0123456789abcdef:20:1", "track": 1})

        same_band = policy.enrich(frame(21), {"risk_band": "attention"}, now_ms=10_999)
        self.assertNotIn("voice_prompt", same_band)
        repeat = policy.enrich(frame(22), {"risk_band": "attention"}, now_ms=11_000)
        self.assertEqual(repeat["voice_prompt"]["track"], 1)

        high = policy.enrich(frame(23), {"risk_band": "high"}, now_ms=11_100)
        self.assertEqual(high["voice_prompt"]["track"], 2)

    def test_low_clears_and_downgrade_waits_for_the_next_reminder(self) -> None:
        policy = VoicePromptPolicy(repeat_interval_ms=10_000)
        policy.enrich(frame(30), {"risk_band": "critical"}, now_ms=1_000)

        downgrade = policy.enrich(frame(31), {"risk_band": "high"}, now_ms=2_000)
        self.assertNotIn("voice_prompt", downgrade)
        delayed = policy.enrich(frame(32), {"risk_band": "high"}, now_ms=11_999)
        self.assertNotIn("voice_prompt", delayed)
        reminder = policy.enrich(frame(33), {"risk_band": "high"}, now_ms=12_000)
        self.assertEqual(reminder["voice_prompt"]["track"], 2)

        low = policy.enrich(frame(34), {"risk_band": "low"}, now_ms=12_100)
        self.assertNotIn("voice_prompt", low)
        reentry = policy.enrich(frame(35), {"risk_band": "attention"}, now_ms=12_200)
        self.assertEqual(reentry["voice_prompt"]["track"], 1)

    def test_boot_sessions_are_isolated(self) -> None:
        policy = VoicePromptPolicy(repeat_interval_ms=10_000)
        first = policy.enrich(frame(40), {"risk_band": "high"}, now_ms=1_000)
        restarted = FrameEnvelope(
            device_id="aix-helmet-01", boot_id="fedcba9876543210", frame_seq=1,
            capture_ts_ms=400, source_ip="192.168.137.20", jpeg=JPEG_A, received_ts_ms=10_001,
        )
        second = policy.enrich(restarted, {"risk_band": "high"}, now_ms=1_100)

        self.assertEqual(first["voice_prompt"]["command_id"], "0123456789abcdef:40:2")
        self.assertEqual(second["voice_prompt"]["command_id"], "fedcba9876543210:1:2")


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
                "voice_ack": {
                    "requested": "voice_prompt" in payload,
                    "command_id": payload.get("voice_prompt", {}).get("command_id", ""),
                    "track": payload.get("voice_prompt", {}).get("track", 0),
                    "accepted": True,
                    "duplicate": False,
                    "status": "queued",
                },
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
