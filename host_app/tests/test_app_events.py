import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.app import MainWindow


class MainWindowEventRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def make_window(self, root: str) -> MainWindow:
        window = MainWindow()
        window.session_recorder.root = Path(root)
        return window

    def test_routes_camera_status_to_active_chain_stage(self):
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            window._handle_raw_line(
                '{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,'
                '"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg",'
                '"frame_bytes":18432,"fps":5.0,"frames_ok":12,"capture_failures":0,'
                '"psram":false,"valid":true}'
            )
            self.assertIn("320×240", window.dashboard.camera_stage.meta.text())
            self.assertIn("5.00 帧/秒", window.dashboard.camera_stage.meta.text())
            window.close()

    def test_routes_action_status_to_diagnostic_protocol(self):
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            window._handle_raw_line(
                '{"type":"action_status","version":1,"ts_ms":4200,"frame_seq":17,'
                '"risk_score":71,"valid":true,"stale":false,'
                '"action_state":"high","rgb_pattern":"orange_blink_2hz"}'
            )
            self.assertIn("橙灯快速闪烁", window.dashboard.protocol_log.toPlainText())
            window.close()

    def test_legacy_preview_event_does_not_change_pc_frame_source(self):
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            service_url = window.chain_client.service_url
            window._handle_raw_line(
                '{"type":"camera_preview","version":1,"valid":true,'
                '"url":"http://192.168.137.23:8081/capture.jpg",'
                '"ip":"192.168.137.23","port":8081,"reason":"ready"}'
            )
            self.assertEqual(window.chain_client.service_url, service_url)
            self.assertNotIn("192.168.137.23", window.dashboard.frame_telemetry.text())
            window.close()

    def test_chain_state_updates_risk_and_same_frame_action_ack(self):
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            window._accept_chain_state({
                "type": "chain_state", "device_id": "aix-helmet-01", "boot_id": "0123456789abcdef",
                "upload": {"state": "healthy", "last_frame_seq": 18, "fps": 2.5, "frame_age_ms": 100},
                "model": {"state": "ready", "latency_ms": 90.0, "gpu": "cuda", "error": ""},
                "callback": {"state": "confirmed", "latency_ms": 40.0},
                "risk": {"valid": True, "score": 72, "band": "high", "reason": "car_approaching", "dominant_class": "car", "frame_seq": 18},
                "action": {"confirmed": True, "state": "high", "rgb_pattern": "orange_blink_2hz", "frame_seq": 18, "stale": False},
                "last_error": "",
            })
            self.assertEqual(window.dashboard.risk_score.text(), "72")
            self.assertIn("第 18 帧", window.dashboard.action_ack.text())
            window.close()


if __name__ == "__main__":
    unittest.main()
