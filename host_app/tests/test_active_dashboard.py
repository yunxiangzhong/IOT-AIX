import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from aix_host_app.app import MainWindow
from aix_host_app.models import ActionStatusEvent, PneumaticStatusEvent
from aix_host_app.widgets.active_dashboard import ActiveVisionDashboard
from aix_host_app.widgets.pneumatic_calibration_panel import PneumaticCalibrationPanel


class ActiveVisionDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_switches_between_display_and_diagnostic_modes(self):
        dashboard = ActiveVisionDashboard()
        self.assertTrue(dashboard.diagnostics.isHidden())
        dashboard.set_diagnostic_mode(True)
        self.assertFalse(dashboard.diagnostics.isHidden())
        self.assertEqual(dashboard.diagnostics.count(), 5)
        self.assertIn("未从设备读取", dashboard.pneumatic_panel.threshold_snapshot.toPlainText())
        dashboard.set_diagnostic_mode(False)
        self.assertTrue(dashboard.diagnostics.isHidden())

    def test_threshold_save_reports_success_only_after_esp_config_confirmation(self):
        panel = PneumaticCalibrationPanel()
        panel.target_kpa.setValue(8.0)
        panel._save_calibration()
        panel.apply_command_result({"accepted": True, "command_id": "save-8", "error": ""})
        self.assertIn("正在读取 ESP32", panel.status.text())
        panel.apply_config({
            "target_kpa": 8.0, "max_kpa": 12.0, "max_inflate_ms": 5000,
            "calibration_valid": True, "automatic_enabled": True,
        })
        self.assertIn("参数保存并回读确认成功", panel.status.text())
        self.assertIn("8.0 kPa", panel.status.text())

    def test_threshold_save_does_not_succeed_when_any_roundtrip_value_differs(self):
        expected = {"target_kpa": 8.0, "max_kpa": 12.0, "max_inflate_ms": 5000}
        for key, actual in (("target_kpa", 8.1), ("max_kpa", 13.0), ("max_inflate_ms", 4900)):
            with self.subTest(key=key):
                panel = PneumaticCalibrationPanel()
                panel._save_calibration()
                returned = dict(expected)
                returned[key] = actual
                returned.update(calibration_valid=True, automatic_enabled=True)

                panel.apply_config(returned)

                self.assertNotIn("成功", panel.status.text())

    def test_pneumatic_panel_defaults_to_five_second_inflation_limit(self):
        panel = PneumaticCalibrationPanel()

        self.assertEqual(panel.target_kpa.value(), 8.0)
        self.assertEqual(panel.max_kpa.value(), 12.0)
        self.assertEqual(panel.max_inflate_ms.value(), 5000)

    def test_pneumatic_status_allows_mpu_protection_when_vision_is_stale(self):
        dashboard = ActiveVisionDashboard()
        event = PneumaticStatusEvent(
            ts_ms=1000, state="idle", fault="none", trigger="none", operation=0,
            pump_on=False, valve_on=False, pressure_kpa=8.0,
            pressure_valid=True, pressure_age_ms=200, vision_state="stale",
            vision_fresh=False, mpu_available=True, mpu_calibrated=True,
            impact=False, rapid_tilt=False, automatic_enabled=True,
            pump_verified=True, valve_verified=True, self_test_failed=False,
        )

        dashboard.apply_pneumatic_status(event)

        self.assertIn("允许：安全条件有效", dashboard.derived_values["pressure"].text())

    def test_pneumatic_status_blocks_protection_when_pump_is_unverified(self):
        dashboard = ActiveVisionDashboard()
        event = PneumaticStatusEvent(
            ts_ms=1000, state="idle", fault="none", trigger="none", operation=0,
            pump_on=False, valve_on=False, pressure_kpa=8.0,
            pressure_valid=True, pressure_age_ms=10, vision_state="safe",
            vision_fresh=True, mpu_available=True, mpu_calibrated=True,
            impact=False, rapid_tilt=False, automatic_enabled=True,
            pump_verified=False, valve_verified=True, self_test_failed=False,
        )

        dashboard.apply_pneumatic_status(event)

        self.assertIn("禁止：泵自检未通过", dashboard.derived_values["pressure"].text())

    def test_pneumatic_status_blocks_protection_when_pressure_is_older_than_200_ms(self):
        dashboard = ActiveVisionDashboard()
        event = PneumaticStatusEvent(
            ts_ms=1000, state="idle", fault="none", trigger="none", operation=0,
            pump_on=False, valve_on=False, pressure_kpa=8.0,
            pressure_valid=True, pressure_age_ms=201, vision_state="safe",
            vision_fresh=True, mpu_available=True, mpu_calibrated=True,
            impact=False, rapid_tilt=False, automatic_enabled=True,
            pump_verified=True, valve_verified=True, self_test_failed=False,
        )

        dashboard.apply_pneumatic_status(event)

        self.assertIn("禁止：压力无效或过期", dashboard.derived_values["pressure"].text())

    def test_self_test_waits_for_vented_state_before_dispatch(self):
        panel = PneumaticCalibrationPanel()
        commands = []
        panel.command_requested.connect(commands.append)
        base = dict(
            ts_ms=1000, fault="none", trigger="none", operation=0,
            pump_on=False, valve_on=False, pressure_kpa=5.5,
            pressure_valid=True, pressure_age_ms=10, vision_state="safe",
            vision_fresh=True, mpu_available=True, mpu_calibrated=True,
            impact=False, rapid_tilt=False,
        )
        panel.apply_status(PneumaticStatusEvent(state="cooldown", **base))
        panel._request_self_test()
        self.assertEqual(commands[-1]["command"], "vent")

        panel.apply_status(PneumaticStatusEvent(state="vented", **base))
        QtWidgets.QApplication.processEvents()
        self.assertEqual(commands[-1]["command"], "self_test")

    def test_renders_risk_action_and_stale_states(self):
        dashboard = ActiveVisionDashboard()
        dashboard.apply_chain_state({
            "device_id": "aix-helmet-01",
            "upload": {"state": "healthy", "last_frame_seq": 18, "fps": 2.48, "frame_age_ms": 120},
            "model": {"state": "ready", "latency_ms": 1635.0, "gpu": "cuda", "error": ""},
            "callback": {"state": "confirmed", "latency_ms": 84.0},
            "risk": {"valid": True, "score": 71, "band": "high", "reason": "scene_proximity", "frame_seq": 18},
            "action": {"confirmed": True, "state": "high", "rgb_pattern": "orange_blink_2hz", "frame_seq": 18, "stale": False},
            "last_error": "",
        })
        self.assertEqual(dashboard.risk_score.text(), "71")
        self.assertIn("高风险", dashboard.risk_band.text())
        self.assertIn("橙灯", dashboard.action_pattern.text())
        self.assertIn("高风险已触发充气", dashboard.derived_values["mpu6050"].text())
        self.assertNotIn("MPU", dashboard.derived_values["mpu6050"].text())

        dashboard.apply_chain_state({
            "device_id": "aix-helmet-01",
            "upload": {"state": "failed", "last_frame_seq": 18, "fps": 0, "frame_age_ms": 3400},
            "model": {"state": "error", "latency_ms": None, "gpu": "cuda", "error": "model stopped"},
            "callback": {"state": "failed", "latency_ms": None},
            "risk": {"valid": False, "score": 0, "band": "low", "reason": ""},
            "action": {"confirmed": True, "state": "fault", "rgb_pattern": "purple_blink_1hz", "frame_seq": 18, "stale": True},
            "last_error": "model stopped",
        })
        self.assertEqual(dashboard.risk_score.text(), "--")
        self.assertIn("失效", dashboard.risk_band.text())
        self.assertIn("紫灯", dashboard.action_pattern.text())

    def test_health_ready_updates_model_stage_before_first_frame(self):
        dashboard = ActiveVisionDashboard()

        dashboard.apply_health({
            "model": "DA3-SMALL",
            "model_state": "ready",
            "model_ready": True,
            "gpu": "cuda",
            "model_error": "",
        })

        self.assertIn("已就绪", dashboard.model_value.text())
        self.assertIn("已就绪", dashboard.model_stage.meta.text())
        self.assertIn("等待视觉帧", dashboard.risk_reason.text())

    def test_health_poll_cannot_reset_an_existing_chain_result(self):
        dashboard = ActiveVisionDashboard()
        dashboard.apply_chain_state({
            "revision": 8,
            "device_id": "aix-helmet-01",
            "upload": {"state": "healthy", "last_frame_seq": 18, "fps": 1.0, "frame_age_ms": 120},
            "model": {"state": "ready", "name": "DA3-SMALL", "latency_ms": 180.0, "gpu": "cuda", "error": ""},
            "callback": {"state": "confirmed", "latency_ms": 40.0},
            "risk": {"valid": True, "score": 71, "band": "high", "reason": "car_proximity", "frame_seq": 18},
            "action": {"confirmed": True, "state": "high", "rgb_pattern": "orange_blink_2hz", "frame_seq": 18, "stale": False},
            "last_error": "",
        })
        result_before = (
            dashboard.risk_band.text(),
            dashboard.risk_reason.text(),
            dashboard.system_status.text(),
            dashboard.decision_model.text(),
        )

        dashboard.apply_health({
            "model": "DA3-SMALL",
            "model_state": "ready",
            "model_ready": True,
            "gpu": "cuda",
            "model_error": "",
        })

        self.assertEqual((
            dashboard.risk_band.text(),
            dashboard.risk_reason.text(),
            dashboard.system_status.text(),
            dashboard.decision_model.text(),
        ), result_before)

    def test_decision_panel_exposes_live_frame_model_callback_and_freshness(self):
        dashboard = ActiveVisionDashboard()
        dashboard.apply_chain_state({
            "device_id": "aix-helmet-01",
            "boot_id": "0123456789abcdef",
            "upload": {"state": "healthy", "last_frame_seq": 18, "fps": 2.48, "frame_age_ms": 120},
            "model": {"state": "ready", "latency_ms": 1635.0, "gpu": "cuda", "error": ""},
            "callback": {"state": "confirmed", "latency_ms": 84.0, "attempts": 1},
            "risk": {"valid": True, "score": 71, "band": "high", "reason": "scene_proximity", "frame_seq": 18},
            "action": {"confirmed": True, "state": "high", "rgb_pattern": "orange_blink_2hz", "frame_seq": 18, "stale": False},
            "last_error": "",
        })

        self.assertIn("第 00000018 帧", dashboard.decision_frame.text())
        self.assertIn("已就绪", dashboard.decision_model.text())
        self.assertIn("1635", dashboard.decision_model.text())
        self.assertIn("已确认", dashboard.decision_callback.text())
        self.assertIn("84", dashboard.decision_callback.text())
        self.assertIn("120", dashboard.decision_freshness.text())
        self.assertIn("2.48", dashboard.decision_freshness.text())
        self.assertEqual(dashboard.decision_panel.minimumWidth(), 0)
        self.assertEqual(
            dashboard.decision_panel.sizePolicy().horizontalPolicy(),
            QtWidgets.QSizePolicy.Policy.Ignored,
        )

    def test_default_display_uses_chinese_product_copy(self):
        dashboard = ActiveVisionDashboard()
        dashboard.apply_chain_state({
            "device_id": "aix-helmet-01",
            "boot_id": "0123456789abcdef",
            "upload": {"state": "healthy", "last_frame_seq": 18, "fps": 2.48, "frame_age_ms": 120},
            "model": {"state": "ready", "latency_ms": 1635.0, "gpu": "cuda", "error": ""},
            "callback": {"state": "confirmed", "latency_ms": 84.0, "attempts": 1},
            "risk": {"valid": True, "score": 71, "band": "high", "reason": "scene_proximity", "frame_seq": 18},
            "action": {"confirmed": True, "state": "high", "rgb_pattern": "orange_blink_2hz", "frame_seq": 18, "stale": False},
            "last_error": "",
        })

        self.assertTrue(dashboard.instrument_subtitle.isHidden())
        self.assertEqual(
            dashboard.sensor_row_keys,
            ("ov5640", "mpu6050", "pressure", "dfplayer", "rgb", "pneumatic"),
        )
        self.assertEqual(dashboard.model_stage.title.text(), "上位机视觉推理")
        self.assertEqual(dashboard.camera_stage.title.text(), "相机采集")
        self.assertEqual(dashboard.upload_stage.title.text(), "图像上传")
        self.assertEqual(dashboard.action_stage.title.text(), "动作反馈")
        self.assertEqual(dashboard.device_value.text(), "头盔设备 01 · 正常")
        self.assertIn("前向场景", dashboard.risk_reason.text())
        self.assertNotIn("scene_proximity", dashboard.risk_reason.text())
        self.assertIn("橙灯", dashboard.action_pattern.text())
        self.assertNotIn("GPIO", dashboard.action_pattern.text())
        self.assertIn("动作已确认", dashboard.action_ack.text())
        self.assertIn("帧/秒", dashboard.upload_stage.meta.text())
        self.assertIn("毫秒", dashboard.model_stage.meta.text())
        self.assertEqual(dashboard.risk_trend.samples[-1], 71)
        self.assertTrue(dashboard.diagnostics.isHidden())

    def test_main_window_uses_pc_chain_client_and_minimum_dashboard_size(self):
        window = MainWindow()
        self.assertIn("YaHei", self.app.font().family())
        self.assertTrue(hasattr(window, "chain_client"))
        self.assertFalse(hasattr(window, "vision_client"))
        self.assertFalse(hasattr(window, "settings_dialog"))
        titles = [label.text() for label in window.findChildren(QtWidgets.QLabel)]
        self.assertEqual(titles.count("AIX 控制中心"), 1)
        self.assertNotIn("AIX 主动视觉安全监控台", titles)
        self.assertGreaterEqual(window.minimumWidth(), 1024)
        self.assertGreaterEqual(window.minimumHeight(), 620)
        window.resize(1280, 720)
        window.show()
        self.app.processEvents()
        self.assertTrue(window.dashboard.safety_note.isHidden())
        window.resize(1440, 900)
        self.app.processEvents()
        self.assertFalse(window.dashboard.safety_note.isHidden())
        window.close()

    def test_main_window_uses_runtime_link_token_for_cooperative_requests(self):
        with mock.patch.dict(os.environ, {"AIX_LINK_TOKEN": "runtime-link-token"}):
            window = MainWindow()
        self.assertEqual(window.chain_client.token, "runtime-link-token")
        window.close()

    def test_chain_timeout_preserves_healthy_model_and_recovers_same_revision(self):
        class ExpiredClock:
            def elapsed(self):
                return 4000

            def restart(self):
                return 0

        window = MainWindow()
        window.chain_client.stop()
        window._watchdog_timer.stop()
        window._last_health = {
            "model": "DA3-SMALL", "model_state": "loading", "model_ready": False,
            "gpu": "cuda", "model_error": "",
        }
        window._last_chain_state = {
            "revision": 7,
            "device_id": "aix-helmet-01",
            "upload": {"state": "healthy", "last_frame_seq": 18, "fps": 1.0},
            "model": {"state": "ready", "name": "DA3-SMALL", "gpu": "cuda"},
            "callback": {"state": "confirmed"},
            "risk": {"valid": True, "score": 71, "band": "high", "frame_seq": 18},
            "action": {"confirmed": True, "state": "high", "frame_seq": 18, "stale": False},
        }
        window._chain_clock = ExpiredClock()

        window._check_chain_timeout()

        self.assertTrue(window._watchdog_fault_shown)
        window._accept_health({
            "model": "DA3-SMALL", "model_state": "ready", "model_ready": True,
            "gpu": "cuda", "model_error": "",
        })
        self.assertIn("CUDA GPU", window.dashboard.model_value.text())
        self.assertIn("已就绪", window.dashboard.model_value.text())

        recovered = dict(window._last_chain_state)
        window._accept_chain_state(recovered)
        self.assertFalse(window._watchdog_fault_shown)
        self.assertIn("1.00", window.dashboard.upload_stage.meta.text())
        window.close()

    def test_compact_height_prioritizes_core_closed_loop_information(self):
        dashboard = ActiveVisionDashboard()
        dashboard.set_compact_mode(True)
        self.assertTrue(dashboard.risk_trend.isHidden())
        self.assertTrue(dashboard.safety_note.isHidden())

        dashboard.set_compact_mode(False)
        self.assertTrue(dashboard.risk_trend.isHidden())
        self.assertFalse(dashboard.safety_note.isHidden())
        dashboard.close()

    def test_serial_action_status_does_not_overwrite_pc_risk_card(self):
        dashboard = ActiveVisionDashboard()
        dashboard.apply_chain_state({
            "revision": 4,
            "device_id": "aix-helmet-01",
            "boot_id": "0123456789abcdef",
            "upload": {"state": "healthy", "last_frame_seq": 18, "fps": 1.0, "frame_age_ms": 120},
            "model": {"state": "ready", "latency_ms": 180.0, "gpu": "cuda", "error": ""},
            "callback": {"state": "confirmed", "latency_ms": 40.0},
            "risk": {"valid": True, "score": 71, "band": "high", "reason": "car_proximity", "frame_seq": 18},
            "action": {"confirmed": True, "state": "high", "rgb_pattern": "orange_blink_2hz", "frame_seq": 18, "stale": False, "e2e_latency_ms": 512},
            "display": {"ready": True, "boot_id": "0123456789abcdef", "frame_seq": 18, "capture_ts_ms": 7200, "detections": []},
            "last_error": "",
        })

        dashboard.apply_action_status(ActionStatusEvent(
            ts_ms=9000,
            frame_seq=17,
            risk_score=5,
            valid=True,
            stale=False,
            action_state="safe",
            rgb_pattern="green_solid",
        ))

        self.assertEqual(dashboard.risk_score.text(), "71")
        self.assertIn("第 18 帧", dashboard.action_ack.text())
        self.assertIn("端到端 512 毫秒", dashboard.action_ack.text())

        stage_before = dashboard.action_stage.meta.text()
        ack_before = dashboard.action_ack.text()
        dashboard.apply_action_status(ActionStatusEvent(
            ts_ms=9100,
            frame_seq=18,
            risk_score=5,
            valid=True,
            stale=False,
            action_state="safe",
            rgb_pattern="green_solid",
        ))
        self.assertEqual(dashboard.action_stage.meta.text(), stage_before)
        self.assertEqual(dashboard.action_ack.text(), ack_before)

    def test_snapshot_updates_image_and_matching_risk_together(self):
        dashboard = ActiveVisionDashboard()
        image = QtGui.QImage(320, 240, QtGui.QImage.Format.Format_RGB32)
        image.fill(QtGui.QColor("#345678"))
        buffer = QtCore.QBuffer()
        buffer.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
        self.assertTrue(image.save(buffer, "JPG"))
        state = {
            "revision": 7,
            "device_id": "aix-helmet-01", "boot_id": "0123456789abcdef",
            "upload": {"state": "healthy", "last_frame_seq": 20, "fps": 1.0, "frame_age_ms": 80},
            "model": {"state": "ready", "latency_ms": 210.0, "gpu": "cuda", "error": ""},
            "callback": {"state": "confirmed", "latency_ms": 30.0},
            "risk": {"valid": True, "score": 42, "band": "attention", "reason": "car_proximity", "frame_seq": 20},
            "action": {"confirmed": True, "state": "attention", "rgb_pattern": "yellow_blink_1hz", "frame_seq": 20, "stale": False},
            "display": {
                "ready": True, "boot_id": "0123456789abcdef", "frame_seq": 20,
                "capture_ts_ms": 8000,
                "detections": [{"class_name": "car", "score": 0.91, "bbox_norm": [0.1, 0.2, 0.5, 0.8], "risk_score": 42}],
            },
            "last_error": "",
        }

        self.assertTrue(dashboard.apply_snapshot(bytes(buffer.data()), 20, 8000, state))

        self.assertEqual(dashboard.risk_score.text(), "42")
        self.assertIn("第 00000020 帧", dashboard.frame_telemetry.text())
        self.assertEqual(dashboard.camera_image.detections[0]["class_name"], "car")


if __name__ == "__main__":
    unittest.main()
