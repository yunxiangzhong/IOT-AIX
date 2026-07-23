import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from frame_pipeline import FrameEnvelope, LatestFrameStore
from pneumatic_proxy import PneumaticProtocolError, PneumaticProxy, StaleDeviceError
from app import create_app


class PneumaticProxyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.store = LatestFrameStore()
        self.store.put(
            FrameEnvelope(
                device_id="aix-helmet-01",
                boot_id="0123456789abcdef",
                frame_seq=8,
                capture_ts_ms=3200,
                source_ip="192.168.137.20",
                jpeg=b"jpeg",
                received_ts_ms=10_000,
            )
        )

    def test_forwards_command_only_to_fresh_latest_device_and_checks_ack_identity(self) -> None:
        calls = []

        def transport(url, token, payload, timeout_s):
            calls.append((url, token, payload, timeout_s))
            return {
                "type": "pneumatic_ack",
                "version": 1,
                "boot_id": "0123456789abcdef",
                "command_id": payload["command_id"],
                "accepted": True,
                "duplicate": False,
                "state": "vented",
                "fault": "none",
            }

        proxy = PneumaticProxy(self.store, token="unit-secret", post_transport=transport, now_ms=lambda: 12_999)
        result = proxy.command(
            "aix-helmet-01",
            {"command_id": "cmd-01", "command": "vent"},
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(calls[0][0], "http://192.168.137.20:8080/pneumatic/command")
        self.assertEqual(calls[0][1], "unit-secret")
        self.assertEqual(calls[0][2]["device_id"], "aix-helmet-01")
        self.assertEqual(calls[0][2]["boot_id"], "0123456789abcdef")

    def test_rejects_stale_device_before_sending_command(self) -> None:
        proxy = PneumaticProxy(self.store, token="unit-secret", now_ms=lambda: 13_001)

        with self.assertRaises(StaleDeviceError):
            proxy.command("aix-helmet-01", {"command_id": "cmd-02", "command": "vent"})

    def test_forwards_hardware_self_test_without_calibration_fields(self) -> None:
        sent = []

        def transport(_url, _token, payload, _timeout_s):
            sent.append(payload)
            return {
                "type": "pneumatic_ack", "version": 1, "boot_id": "0123456789abcdef",
                "command_id": payload["command_id"], "accepted": True,
            }

        proxy = PneumaticProxy(self.store, token="unit-secret", post_transport=transport, now_ms=lambda: 11_000)
        result = proxy.command("aix-helmet-01", {"command_id": "self-test-01", "command": "self_test"})

        self.assertTrue(result["accepted"])
        self.assertEqual(sent[0]["command"], "self_test")
        self.assertNotIn("target_kpa", sent[0])

    def test_save_calibration_forwards_only_pressure_limits(self) -> None:
        sent = []

        def transport(_url, _token, payload, _timeout_s):
            sent.append(payload)
            return {
                "type": "pneumatic_ack", "version": 1, "boot_id": "0123456789abcdef",
                "command_id": payload["command_id"], "accepted": True,
            }

        proxy = PneumaticProxy(self.store, token="unit-secret", post_transport=transport, now_ms=lambda: 11_000)
        result = proxy.command(
            "aix-helmet-01",
            {"command_id": "save-01", "command": "save_calibration", "target_kpa": 8.0, "max_kpa": 12.0},
        )

        self.assertTrue(result["accepted"])
        self.assertEqual(sent[0]["target_kpa"], 8.0)
        self.assertEqual(sent[0]["max_kpa"], 12.0)
        self.assertNotIn("max_inflate_ms", sent[0])

    def test_rejects_mismatched_ack_boot_or_command_id(self) -> None:
        def transport(_url, _token, payload, _timeout_s):
            return {
                "type": "pneumatic_ack",
                "version": 1,
                "boot_id": "different-boot",
                "command_id": payload["command_id"],
                "accepted": True,
            }

        proxy = PneumaticProxy(self.store, token="unit-secret", post_transport=transport, now_ms=lambda: 11_000)
        with self.assertRaises(PneumaticProtocolError):
            proxy.command("aix-helmet-01", {"command_id": "cmd-03", "command": "vent"})

    def test_preserves_a_device_rejection_when_identity_is_valid(self) -> None:
        def transport(_url, _token, payload, _timeout_s):
            return {
                "type": "pneumatic_ack",
                "version": 1,
                "boot_id": "0123456789abcdef",
                "command_id": payload["command_id"],
                "accepted": False,
                "duplicate": False,
                "error": "calibration_requires_vented_state_and_safe_limits",
            }

        proxy = PneumaticProxy(self.store, token="unit-secret", post_transport=transport, now_ms=lambda: 11_000)
        result = proxy.command("aix-helmet-01", {"command_id": "cmd-04", "command": "vent"})
        self.assertFalse(result["accepted"])
        self.assertIn("vented_state", result["error"])


class PneumaticApiTests(unittest.TestCase):
    def test_exposes_only_proxy_command_and_config_routes(self) -> None:
        calls = []

        class FakeProxy:
            def command(self, device_id, payload):
                calls.append(("command", device_id, payload))
                return {"type": "pneumatic_ack", "version": 1, "accepted": True, "command_id": payload["command_id"]}

            def config(self, device_id):
                calls.append(("config", device_id))
                return {"type": "pneumatic_config", "version": 2, "device_id": device_id}

        app = create_app(None, token="unit-secret", start_worker=False, pneumatic_proxy=FakeProxy())
        client = TestClient(app)
        response = client.post(
            "/v1/pneumatic/command?device_id=aix-helmet-01",
            json={"command_id": "cmd-04", "command": "vent"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["accepted"])
        config = client.get("/v1/pneumatic/config?device_id=aix-helmet-01")
        self.assertEqual(config.status_code, 200)
        self.assertEqual(calls[0][0], "command")
        self.assertEqual(calls[1], ("config", "aix-helmet-01"))


if __name__ == "__main__":
    unittest.main()
