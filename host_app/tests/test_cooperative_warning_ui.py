import os
import unittest
from unittest.mock import Mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.app import MainWindow
from aix_host_app.models import VoiceStatusEvent
from aix_host_app.widgets.cooperative_scenario import scene_geometry


class CooperativeWarningUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_global_navigation_has_real_dashboard_and_labelled_demo_input_page(self):
        window = MainWindow()
        self.assertEqual(window.primary_pages.count(), 2)
        self.assertEqual(window.overview_button.text(), "中控总览")
        self.assertEqual(window.scenario_button.text(), "协同场景")
        self.assertTrue(hasattr(window, "scenario_panel"))
        self.assertTrue(window.scenario_panel.has_simulated_input())
        self.assertEqual(tuple(window.scenario_panel.scene_buttons), (4, 5, 6))
        self.assertIn("演示输入", window.scenario_panel.findChildren(QtWidgets.QLabel)[1].text())
        window.scenario_panel.begin_demo(4)
        window.scenario_panel._update_from_elapsed(1000)
        self.assertIn("链路未就绪", window.scenario_panel.stages[3].meta.text())
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
            }, "automatic_ready": True, "overall": "healthy", "reason": "硬件正常",
        })())
        self.assertEqual(overview.peripheral_values["ov5640"].text(), "正常")
        overview.apply_pressure(type("Pressure", (), {
            "valid": True, "seq": 8, "filtered_kpa": 2.1, "ts_ms": 1200,
        })())
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
                for label in (overview.peripheral_values[key], overview.realtime_values[key], overview.derived_values[key]):
                    self.assertGreaterEqual(label.height(), label.fontMetrics().height())
            self.assertTrue(overview.execution_guard.isVisible())
            self.assertTrue(overview.pneumatic_acceptance_note.isVisible())
        window.close()

    def test_voice_feedback_comes_from_serial_telemetry(self):
        window = MainWindow()
        overview = window.dashboard
        overview.apply_voice_status(VoiceStatusEvent("playing", "road-risk-7", 2, ""))
        self.assertIn("播放中", overview.voice_status_value.text())
        overview.apply_voice_status(VoiceStatusEvent("error", "road-risk-7", 2, "tf_card_not_ready"))
        self.assertIn("错误", overview.voice_status_value.text())
        window.close()

    def test_serial_open_waits_for_real_telemetry_before_claiming_device_connection(self):
        window = MainWindow()
        window.connection_panel.set_ports([])
        window._handle_reader_state("connected")

        self.assertIn("等待真实 AIX 遥测", window.connection_panel.state_label.text())
        self.assertIn("串口已打开", window.device_button.text())

        window._handle_raw_line(
            '{"type":"pressure","version":1,"seq":1,"ts_ms":1000,"raw":100,'
            '"mv":90,"kpa":2.1,"filtered_kpa":2.1,"over_pressure":false,"valid":true}'
        )
        self.assertIn("已确认", window.connection_panel.state_label.text())
        self.assertIn("已连接", window.device_button.text())
        window.close()

    def test_serial_disconnect_releases_reader_for_reconnect(self):
        window = MainWindow()
        stale_reader = Mock()
        stale_reader.isRunning.return_value = False
        window.reader = stale_reader
        window._serial_port = "COM21"
        window._handle_reader_state("disconnected")

        self.assertIsNone(window.reader)
        self.assertEqual(window._serial_port, "")
        window.close()

    def test_scene_005_map_shows_child_not_truck(self):
        """场景 005 显示儿童直道元素，不含货车。"""
        window = MainWindow()
        panel = window.scenario_panel
        panel.set_link_ready(True)
        panel.begin_demo(5)
        panel._update_from_elapsed(500)
        self.assertIn("儿童", panel.detection_value[1].text())
        self.assertNotIn("货车", panel.detection_value[1].text())
        self.assertIn("儿童", panel.stages[0].meta.text())
        window.close()

    def test_scene_006_map_shows_pedestrian_not_truck(self):
        """场景 006 显示行人施工元素，不含货车。"""
        window = MainWindow()
        panel = window.scenario_panel
        panel.set_link_ready(True)
        panel.begin_demo(6)
        panel._update_from_elapsed(500)
        self.assertIn("行人", panel.detection_value[1].text())
        self.assertNotIn("货车", panel.detection_value[1].text())
        self.assertIn("行人", panel.stages[0].meta.text())
        window.close()

    def test_scene_004_map_still_shows_truck(self):
        """场景 004 应仍显示货车元素。"""
        window = MainWindow()
        panel = window.scenario_panel
        panel.set_link_ready(True)
        panel.begin_demo(4)
        panel._update_from_elapsed(300)
        self.assertIn("货车", panel.detection_value[1].text())
        window.close()

    def test_scene_005_geometry_keeps_rider_on_road_and_child_behind_parked_vehicle(self):
        geometry = scene_geometry(5, 1000, 600, progress=0.2, rider_progress=0.2)
        self.assertTrue(geometry["rider_in_road"])
        self.assertTrue(geometry["line_blocked_by_vehicle"])
        self.assertLess(geometry["vehicle"][2], geometry["vehicle"][3])
        self.assertLess(geometry["rider"][1], geometry["road"][1] + geometry["road"][3])

    def test_scene_006_geometry_keeps_rider_in_open_lane_and_pedestrian_behind_fence(self):
        geometry = scene_geometry(6, 1000, 600, progress=0.2, rider_progress=0.2)
        self.assertTrue(geometry["rider_in_open_lane"])
        self.assertTrue(geometry["line_blocked_by_fence"])
        self.assertTrue(geometry["construction_in_opposite_lane"])

    def test_demo_scenes_require_demo_mode_and_restore_real_link(self):
        window = MainWindow()
        panel = window.scenario_panel
        self.assertEqual(panel.mode_button.text(), "进入模拟模式")
        panel.begin_demo(5)
        self.assertIn("模拟模式", panel.stages[3].meta.text())
        panel.set_operating_mode("demo", lease_remaining_ms=15000)
        self.assertEqual(panel.mode_button.text(), "恢复真实链路")
        self.assertTrue(panel.scene_buttons[5].isEnabled())
        panel.reset_demo()
        panel.set_operating_mode("real")
        self.assertEqual(panel.mode_button.text(), "进入模拟模式")
        self.assertFalse(panel._demo_mode)
        window.close()

    def test_scenario_errors_are_differentiated(self):
        """apply_submission_error 应显示具体错误而非统一"服务拒绝"。"""
        window = MainWindow()
        panel = window.scenario_panel
        panel.set_link_ready(True)
        panel.begin_demo(4)
        self.assertTrue(panel._running)

        panel.apply_submission_error("PC 鉴权失败：链路令牌无效")
        self.assertIn("鉴权失败", panel.stages[3].meta.text())

        panel.reset_demo()
        panel.set_link_ready(True)
        panel.begin_demo(5)
        panel.apply_submission_error("未收到头盔最新帧：ESP32 尚未上传检测画面")
        self.assertIn("最新帧", panel.stages[3].meta.text())

        panel.reset_demo()
        panel.set_link_ready(True)
        panel.begin_demo(6)
        panel.apply_submission_error("ESP32:8080 不可达：Connection refused")
        self.assertIn("不可达", panel.stages[3].meta.text())

        panel.reset_demo()
        panel.set_link_ready(True)
        panel.begin_demo(4)
        panel.apply_submission_error("ESP32 拒绝风险事件：rejected")
        self.assertIn("拒绝风险事件", panel.stages[3].meta.text())

        window.close()


if __name__ == "__main__":
    unittest.main()
