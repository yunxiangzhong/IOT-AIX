import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.app import MainWindow
from aix_host_app.models import VoiceStatusEvent


class CooperativeWarningUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_global_navigation_has_only_real_dashboard_and_separate_utilities(self):
        window = MainWindow()
        self.assertEqual(window.primary_pages.count(), 1)
        self.assertEqual(window.overview_button.text(), "中控总览")
        self.assertFalse(hasattr(window, "scenario_button"))
        self.assertFalse(hasattr(window, "scenario_panel"))
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


if __name__ == "__main__":
    unittest.main()
