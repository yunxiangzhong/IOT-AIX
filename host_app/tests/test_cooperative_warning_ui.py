import os
import re
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.app import MainWindow
from aix_host_app.models import RoadHazardStatusEvent, VoiceStatusEvent
from aix_host_app.widgets.cooperative_scenario import CooperativeScenarioPanel


class CooperativeWarningUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_global_navigation_has_nonmodal_device_sheet_and_separate_utilities(self):
        window = MainWindow()
        self.assertEqual(window.primary_pages.count(), 2)
        self.assertEqual(window.overview_button.text(), "中控总览")
        self.assertEqual(window.scenario_button.text(), "协同场景")
        self.assertFalse(hasattr(window, "settings_dialog"))
        self.assertTrue(window.device_window.isHidden())
        self.assertFalse(hasattr(window.connection_panel, "storage_root_edit"))
        self.assertEqual(window.session_button.text(), "会话记录")
        self.assertFalse(hasattr(window, "preferences_button"))
        self.assertFalse(window.dashboard._static_visual_mode)
        window.device_button.setChecked(True)
        self.app.processEvents()
        self.assertTrue(window.device_window.isVisible())
        self.assertGreaterEqual(window.device_window.width(), 420)
        window.device_button.setChecked(False)
        self.assertTrue(window.device_window.isHidden())
        dashboard_height = window.dashboard.sizeHint().height()
        window.diagnostics_button.setChecked(True)
        self.app.processEvents()
        self.assertTrue(window.diagnostics_window.isVisible())
        self.assertIs(window.dashboard.diagnostics.parentWidget(), window.diagnostics_window)
        self.assertEqual(window.dashboard.sizeHint().height(), dashboard_height)
        window.diagnostics_button.setChecked(False)
        self.assertTrue(window.diagnostics_window.isHidden())
        window.close()

    def test_overview_exposes_complete_six_row_causal_mapping(self):
        window = MainWindow()
        overview = window.dashboard
        self.assertEqual(
            overview.sensor_row_keys,
            ("ov5640", "mpu6050", "pressure", "dfplayer", "rgb", "pneumatic"),
        )
        self.assertEqual(overview.peripheral_panel.objectName(), "peripheralPanel")
        self.assertEqual(overview.realtime_panel.objectName(), "realtimePanel")
        self.assertEqual(overview.decision_panel.objectName(), "decisionPanel")
        self.assertIn("DFPlayer", [label.text() for label in overview.peripheral_panel.findChildren(QtWidgets.QLabel)])
        self.assertIn("上位机状态", [label.text() for label in overview.findChildren(QtWidgets.QLabel)])
        self.assertIn("策略建议与真实执行", overview.pneumatic_acceptance_note.text())
        window.close()

    def test_sensor_columns_align_and_surface_rate_update_and_freshness(self):
        window = MainWindow()
        window.resize(1440, 900)
        window.show()
        self.app.processEvents()
        rows = window.dashboard.sensor_mapping_row_geometries()
        self.assertEqual(len(rows), 6)
        for peripheral, realtime, derived in rows:
            self.assertAlmostEqual(peripheral.y(), realtime.y(), delta=2)
            self.assertAlmostEqual(realtime.y(), derived.y(), delta=2)
            self.assertAlmostEqual(peripheral.height(), realtime.height(), delta=2)
            self.assertAlmostEqual(realtime.height(), derived.height(), delta=2)
            self.assertGreaterEqual(peripheral.height(), 64)
        overview = window.dashboard
        overview.apply_camera_status(type("Camera", (), {
            "valid": True, "fps": 9.5, "seq": 7, "ts_ms": 1100, "width": 640, "height": 480,
            "capture_failures": 0, "frames_ok": 7,
        })())
        self.assertEqual(overview.peripheral_values["ov5640"].text(), "等待设备数据")
        overview.apply_hardware_health(type("Health", (), {
            "modules": {
                "ov5640": "healthy", "mpu6050": "healthy", "pressure": "healthy",
                "dfplayer": "healthy", "rgb": "healthy", "pump": "healthy", "valve": "healthy",
            },
            "automatic_ready": True, "overall": "healthy", "reason": "硬件正常",
        })())
        self.assertEqual(overview.peripheral_values["ov5640"].text(), "正常")
        overview.apply_pressure(type("Pressure", (), {"valid": True, "seq": 8, "filtered_kpa": 2.1, "ts_ms": 1200})())
        overview._sensor_received_at_ms["pressure"] -= 1200
        overview.refresh_sensor_freshness()
        self.assertIn("2.10 kPa", overview.realtime_values["pressure"].text())
        self.assertNotIn("ms", overview.realtime_values["pressure"].text())
        window.close()

    def test_layout_is_adaptive_and_core_content_stays_visible(self):
        window = MainWindow()
        for width, height in ((1440, 900), (1280, 720)):
            window.resize(width, height)
            window.show()
            self.app.processEvents()
            overview = window.dashboard
            for widget in (overview.camera_image, overview.peripheral_panel, overview.realtime_panel, overview.decision_panel):
                self.assertTrue(widget.isVisible())
                self.assertGreater(widget.width(), 0)
                self.assertGreater(widget.height(), 0)
            widths = overview.workspace_column_widths()
            camera_share = widths[0] / sum(widths)
            self.assertGreater(camera_share, 0.45)
            self.assertLess(camera_share, 0.66)
            for key in overview.sensor_row_keys:
                for label in (
                    overview.peripheral_values[key], overview.realtime_values[key], overview.derived_values[key]
                ):
                    self.assertGreaterEqual(label.height(), label.fontMetrics().height())
            self.assertTrue(overview.execution_guard.isVisible())
            self.assertTrue(overview.pneumatic_acceptance_note.isVisible())
        window.close()

    def test_voice_rgb_and_serial_feedback_remain_real_feedback(self):
        window = MainWindow()
        overview = window.dashboard
        overview.apply_voice_status(VoiceStatusEvent("playing", "road-risk-7", 2, ""))
        self.assertIn("播放中", overview.voice_status_value.text())
        overview.apply_voice_status(VoiceStatusEvent("error", "road-risk-7", 2, "tf_card_not_ready"))
        self.assertIn("错误", overview.voice_status_value.text())
        window._accept_road_hazard_status(RoadHazardStatusEvent("active", "roadside-test", "high", "orange_blink_2hz", ""))
        self.assertIn("等待真实反馈", window.scenario_panel.voice_value.text())
        self.assertIn("active", window.scenario_panel.serial_status.text())
        window.close()

    def test_scenario_uses_continuous_eta_and_dispatches_after_cloud_prediction(self):
        scene = CooperativeScenarioPanel()
        self.assertEqual(scene.road_map.rider_lane, "northbound_right")
        emitted = []
        scene.start_requested.connect(emitted.append)
        scene.begin_demo()
        first_id = scene.current_event_id
        scene._update_from_elapsed(400)
        eta_early = scene.road_map.eta_seconds
        self.assertEqual(emitted, [])
        scene._update_from_elapsed(900)
        eta_after_cloud = scene.road_map.eta_seconds
        self.assertLess(eta_after_cloud, eta_early)
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0]["event_id"], first_id)
        self.assertLess(emitted[0]["eta_ms"], 5000)
        self.assertIn("下发", scene.stages[3].meta.text())
        scene.reset_demo()
        scene.begin_demo()
        self.assertNotEqual(scene.current_event_id, first_id)

    def test_scene_final_stage_requires_actual_ack_before_deadline(self):
        scene = CooperativeScenarioPanel()
        scene.begin_demo()
        scene._update_from_elapsed(1100)
        event_id = scene.current_event_id
        scene.apply_chain_state({"road_hazard": {
            "event_id": event_id, "delivery": {"state": "completed"},
            "ack": {"state": "completed", "payload": None}, "network_latency_ms": 32,
            "effective_rgb_pattern": "orange_blink_2hz",
        }})
        self.assertIn("等待", scene.stages[-1].meta.text())
        scene.apply_chain_state({"road_hazard": {
            "event_id": event_id, "delivery": {"state": "completed"},
            "ack": {"state": "completed", "payload": {
                "type": "road_hazard_ack", "accepted": True, "event_id": event_id,
                "voice_state": "queued",
            }}, "network_latency_ms": 32, "effective_rgb_pattern": "orange_blink_2hz",
        }})
        self.assertIn("真实 ACK", scene.stages[-1].meta.text())
        self.assertIn("queued", scene.voice_value.text())
        self.assertIsNotNone(scene._ack_remaining_ms)
        self.assertGreater(scene._ack_remaining_ms, 0)

        before_response = scene.road_map.rider_progress
        scene._update_from_elapsed(2100)
        self.assertTrue(scene.road_map.rider_slowed)
        self.assertGreater(scene.road_map.rider_progress, before_response)
        self.assertLess(scene.road_map.rider_progress, 2100 / scene.EVENT_DURATION_MS * 0.82)
        self.assertIn("模拟减速", scene.rider_status[1].text())
        self.assertIn("模拟减速", scene.rider_status[1].text())

    def test_scene_never_fabricates_ack_or_hardware_feedback(self):
        scene = CooperativeScenarioPanel()
        scene.begin_demo()
        scene._update_from_elapsed(3100)
        self.assertFalse(scene._ack_received)
        self.assertFalse(scene.road_map.rider_slowed)
        self.assertIn("等待响应", scene.stages[-1].meta.text())
        scene._update_from_elapsed(scene.EVENT_DURATION_MS)
        self.assertEqual(scene.road_map.eta_seconds, 0.0)
        self.assertAlmostEqual(scene.road_map.progress, 1.0)

    def test_scene_marks_late_ack_and_delivery_failure_as_failed(self):
        scene = CooperativeScenarioPanel()
        scene.begin_demo()
        scene._update_from_elapsed(900)
        event_id = scene.current_event_id
        scene.apply_chain_state({"road_hazard": {
            "event_id": event_id, "delivery": {"state": "failed"},
            "ack": {"state": "failed", "payload": None}, "attempts": 4,
            "network_latency_ms": None, "effective_rgb_pattern": "", "error": "ESP32 offline",
        }})
        self.assertIn("失败", scene.stages[3].meta.text())
        self.assertIn("未确认", scene.stages[-1].meta.text())
        scene._update_from_elapsed(5000)
        scene.apply_chain_state({"road_hazard": {
            "event_id": event_id, "delivery": {"state": "completed"},
            "ack": {"state": "completed", "payload": {
                "type": "road_hazard_ack", "accepted": True, "event_id": event_id,
            }},
        }})
        self.assertIn("超过", scene.stages[-1].meta.text())

    def test_scene_surfaces_real_submission_rejection(self):
        scene = CooperativeScenarioPanel()
        scene.begin_demo()
        scene._update_from_elapsed(900)
        scene.apply_submission_error("未配置路侧协同 Token")
        self.assertIn("下发失败", scene.stages[3].meta.text())
        self.assertIn("未到达 ESP32", scene.stages[4].meta.text())
        self.assertIn("Token", scene.helmet_status[1].text())


if __name__ == "__main__":
    unittest.main()
