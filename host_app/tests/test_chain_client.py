import unittest

from PySide6 import QtCore

from aix_host_app.chain_client import (
    SNAPSHOT_POLL_INTERVAL_MS,
    PcChainClient,
    build_scenario_request,
    build_demo_reset_payload,
    build_collision_ack_payload,
    frame_identity_from_state,
    normalize_service_url,
)


class ChainClientTests(unittest.TestCase):
    def test_static_snapshot_polling_is_half_second(self):
        self.assertEqual(SNAPSHOT_POLL_INTERVAL_MS, 500)

    def test_normalizes_service_url_and_extracts_frame_identity(self):
        self.assertEqual(normalize_service_url("http://127.0.0.1:8008/"), "http://127.0.0.1:8008")
        self.assertEqual(
            frame_identity_from_state({
                "boot_id": "ffffffffffffffff",
                "upload": {"last_frame_seq": 19},
                "display": {"ready": True, "boot_id": "0123456789abcdef", "frame_seq": 17},
            }),
            ("0123456789abcdef", 17),
        )

    def test_rejects_invalid_state_identity(self):
        self.assertIsNone(frame_identity_from_state({"display": {"ready": False, "boot_id": "", "frame_seq": -1}}))

    def test_scenario_request_carries_link_token(self):
        request = build_scenario_request("http://127.0.0.1:8008/v1/scenario-risk", "unit-secret")
        self.assertEqual(request.rawHeader("X-AIX-Token"), b"unit-secret")

    def test_demo_reset_payload_carries_session_identity(self):
        self.assertEqual(
            build_demo_reset_payload("helmet-01", "demo-session"),
            {"device_id": "helmet-01", "session_id": "demo-session"},
        )

    def test_collision_ack_payload_carries_real_boot_and_impact_identity(self):
        self.assertEqual(
            build_collision_ack_payload("helmet-01", "0123456789abcdef", 7),
            {
                "device_id": "helmet-01",
                "boot_id": "0123456789abcdef",
                "impact_count": 7,
            },
        )
        with self.assertRaises(ValueError):
            build_collision_ack_payload("helmet-01", "bad", 7)

    # --- link readiness ---

    def test_link_not_ready_without_token(self):
        client = PcChainClient("http://127.0.0.1:8008", "dev-01", link_token="")
        self.assertFalse(client.is_link_ready())

    def test_link_not_ready_without_url(self):
        client = PcChainClient("", "dev-01", link_token="tok")
        self.assertFalse(client.is_link_ready())

    def test_link_ready_with_full_config(self):
        client = PcChainClient("http://127.0.0.1:8008", "dev-01", link_token="tok")
        self.assertTrue(client.is_link_ready())

    def test_stop_allows_abort_callbacks_to_remove_semantic_pending_entries(self):
        client = PcChainClient(
            "http://127.0.0.1:8008", "dev-01", link_token="tok"
        )

        class ReplyWithSynchronousFinished:
            def abort(self):
                client._semantic_pending.pop("first", None)

        client._semantic_pending = {
            "first": {"replies": [ReplyWithSynchronousFinished()]},
            "second": {"replies": []},
        }

        client.stop()

        self.assertEqual(client._semantic_pending, {})

    # --- scenario error mapping ---

    def test_auth_failure_401(self):
        msg = PcChainClient._map_scenario_error(401, "invalid link token", "fallback")
        self.assertIn("鉴权失败", msg)

    def test_no_recent_frame_503(self):
        msg = PcChainClient._map_scenario_error(503, "no recent frame for device; cannot route to ESP32", "f")
        self.assertIn("未收到头盔最新帧", msg)

    def test_esp32_unreachable_503(self):
        msg = PcChainClient._map_scenario_error(503, "ESP32 health endpoint unreachable at 192.168.1.1:8080", "f")
        self.assertIn("不可达", msg)

    def test_esp32_unreachable_502(self):
        msg = PcChainClient._map_scenario_error(502, "ESP32 /risk call failed at 192.168.1.1:8080", "f")
        self.assertIn("不可达", msg)

    def test_esp32_identity_mismatch_502(self):
        msg = PcChainClient._map_scenario_error(502, "ESP32 identity mismatch at 192.168.1.1:8080", "f")
        self.assertIn("身份不匹配", msg)

    def test_esp32_rejected_502(self):
        msg = PcChainClient._map_scenario_error(502, "ESP32 rejected scenario risk at 192.168.1.1:8080", "f")
        self.assertIn("拒绝风险事件", msg)

    def test_invalid_params_422(self):
        msg = PcChainClient._map_scenario_error(422, "scene_id must be 4, 5, or 6", "f")
        self.assertIn("参数无效", msg)

    def test_unknown_error_uses_fallback(self):
        msg = PcChainClient._map_scenario_error(500, "", "unknown server error")
        self.assertEqual(msg, "unknown server error")


if __name__ == "__main__":
    unittest.main()
