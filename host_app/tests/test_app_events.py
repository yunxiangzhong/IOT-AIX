import os
import json
import tempfile
import unittest
from unittest.mock import Mock
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from aix_host_app.app import MainWindow
from aix_host_app.models import PneumaticStatusEvent


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

    def test_pc_snapshot_is_displayed_from_materialized_png(self):
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            try:
                image = QtGui.QImage(16, 12, QtGui.QImage.Format.Format_RGB32)
                image.fill(QtGui.QColor("#234567"))
                buffer = QtCore.QBuffer()
                buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
                self.assertTrue(image.save(buffer, "JPG"))
                state = {
                    "type": "chain_state", "device_id": "aix-helmet-01", "boot_id": "0123456789abcdef",
                    "display": {"ready": True, "boot_id": "0123456789abcdef", "frame_seq": 19, "capture_ts_ms": 7600, "detections": []},
                    "upload": {}, "model": {}, "callback": {}, "risk": {}, "action": {},
                }

                window._accept_pc_snapshot(bytes(buffer.data()), 19, 7600, state)

                snapshot_path = Path(root) / "latest_processed.png"
                self.assertTrue(snapshot_path.exists())
                self.assertEqual(snapshot_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
                self.assertIn("第 00000019 帧", window.dashboard.frame_telemetry.text())
                self.assertIn("PC PNG 静态快照", window.dashboard.frame_telemetry.text())
            finally:
                window.close()

    def test_new_impact_opens_one_alert_and_updates_existing_alert_for_count_two(self):
        impact = (
            '{"type":"motion","version":2,"seq":201,"ts_ms":4200,'
            '"accel_g":{"x":0.0,"y":0.0,"z":2.31},'
            '"gyro_dps":{"x":1.0,"y":2.0,"z":3.0},'
            '"accel_norm_g":2.31,"accel_delta_g":1.31,"sample_interval_ms":10,'
            '"impact_event":true,"impact_count":1,"tilt_deg":3.0,"impact":true,'
            '"rapid_tilt":false,"danger_latched":true,"calibrated":true,'
            '"speed_mps":0.0,"speed_valid":false}'
        )
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            try:
                window._handle_raw_line(impact)
                window._handle_raw_line(impact)
                self.assertTrue(window.collision_alert_dialog.isVisible())
                self.assertEqual(window.collision_total, 1)

                window._handle_raw_line(impact.replace('"seq":201', '"seq":202').replace('"impact_count":1', '"impact_count":2'))
                self.assertEqual(window.collision_total, 2)
                self.assertIn("2", window.collision_alert_dialog.count_label.text())
            finally:
                window.close()

    def test_collision_ack_only_clears_host_alert_without_pneumatic_or_voice_command(self):
        impact = (
            '{"type":"motion","version":2,"seq":201,"ts_ms":4200,'
            '"accel_g":{"x":0.0,"y":0.0,"z":2.31},'
            '"gyro_dps":{"x":1.0,"y":2.0,"z":3.0},'
            '"accel_norm_g":2.31,"accel_delta_g":1.31,"sample_interval_ms":10,'
            '"impact_event":true,"impact_count":1,"tilt_deg":3.0,"impact":true,'
            '"rapid_tilt":false,"danger_latched":true,"calibrated":true,'
            '"speed_mps":0.0,"speed_valid":false}'
        )
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            try:
                window.chain_client.send_pneumatic_command = Mock()
                window._handle_raw_line(impact)
                window.collision_alert_dialog.ack_button.click()
                self.app.processEvents()

                self.assertFalse(window.collision_alert_dialog.isVisible())
                window.chain_client.send_pneumatic_command.assert_not_called()
            finally:
                window.close()

    def test_latched_legacy_impact_or_rapid_tilt_does_not_open_collision_alert(self):
        legacy_latched_impact = (
            '{"type":"motion","version":2,"seq":201,"ts_ms":4200,'
            '"accel_g":{"x":0.0,"y":0.0,"z":2.31},'
            '"gyro_dps":{"x":1.0,"y":2.0,"z":3.0},'
            '"accel_norm_g":2.31,"accel_delta_g":1.31,"sample_interval_ms":10,'
            '"tilt_deg":3.0,"impact":true,"rapid_tilt":true,'
            '"danger_latched":true,"calibrated":true,'
            '"speed_mps":0.0,"speed_valid":false}'
        )
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            try:
                window._handle_raw_line(legacy_latched_impact)
                self.assertFalse(window.collision_alert_dialog.isVisible())
                self.assertIsNone(window.active_collision_id)
            finally:
                window.close()

    def test_alert_immediately_shows_last_live_pneumatic_feedback(self):
        impact = (
            '{"type":"motion","version":2,"seq":201,"ts_ms":4200,'
            '"accel_g":{"x":0.0,"y":0.0,"z":2.31},'
            '"gyro_dps":{"x":1.0,"y":2.0,"z":3.0},'
            '"accel_norm_g":2.31,"accel_delta_g":1.31,"sample_interval_ms":10,'
            '"impact_event":true,"impact_count":1,"tilt_deg":3.0,"impact":true,'
            '"rapid_tilt":false,"danger_latched":true,"calibrated":true,'
            '"speed_mps":0.0,"speed_valid":false}'
        )
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            try:
                window.latest_pneumatic_status = PneumaticStatusEvent(
                    ts_ms=4100, state="inflating", fault="none", trigger="impact",
                    operation=2, pump_on=True, valve_on=True, pressure_kpa=15.0,
                    pressure_valid=True, pressure_age_ms=10, vision_state="safe",
                    vision_fresh=True, mpu_available=True, mpu_calibrated=True,
                    impact=True, rapid_tilt=False, pump_verified=True,
                    valve_verified=True, automatic_enabled=True,
                )
                window._handle_raw_line(impact)

                self.assertIn("inflating", window.collision_alert_dialog.pneumatic_label.text())
                self.assertIn("安全条件有效", window.collision_alert_dialog.readiness_label.text())
            finally:
                window.close()

    def test_collision_log_records_pressure_transition_but_deduplicates_same_heartbeat(self):
        impact = (
            '{"type":"motion","version":2,"seq":201,"ts_ms":4200,'
            '"accel_g":{"x":0.0,"y":0.0,"z":2.31},'
            '"gyro_dps":{"x":1.0,"y":2.0,"z":3.0},'
            '"accel_norm_g":2.31,"accel_delta_g":1.31,"sample_interval_ms":10,'
            '"impact_event":true,"impact_count":1,"tilt_deg":3.0,"impact":true,'
            '"rapid_tilt":false,"danger_latched":true,"calibrated":true,'
            '"speed_mps":0.0,"speed_valid":false}'
        )
        pneumatic = {
            "type": "pneumatic_status", "version": 1, "ts_ms": 4210,
            "state": "inflating", "fault": "none", "trigger": "impact",
            "operation": 2, "pump_on": True, "valve_on": True,
            "pressure_kpa": 15.0, "pressure_valid": True, "pressure_age_ms": 10,
            "vision_state": "safe", "vision_fresh": True, "mpu_available": True,
            "mpu_calibrated": True, "impact": True, "rapid_tilt": False,
            "pump_verified": True, "valve_verified": True,
            "self_test_failed": False, "automatic_enabled": True,
        }
        with tempfile.TemporaryDirectory() as root:
            window = self.make_window(root)
            try:
                window._handle_raw_line(impact)
                window._handle_raw_line(json.dumps(pneumatic))
                pneumatic["pressure_age_ms"] = 11
                pneumatic["ts_ms"] = 4211
                window._handle_raw_line(json.dumps(pneumatic))
                pneumatic["pressure_kpa"] = 16.0
                pneumatic["ts_ms"] = 4220
                window._handle_raw_line(json.dumps(pneumatic))

                collision_path = window.session_recorder.session_dir / "collision_events.jsonl"
                updates = [
                    json.loads(line) for line in collision_path.read_text(encoding="utf-8").splitlines()
                    if json.loads(line)["event"] == "pneumatic_update"
                ]
                self.assertEqual([item["pressure_kpa"] for item in updates], [15.0, 16.0])
            finally:
                window.close()


if __name__ == "__main__":
    unittest.main()
