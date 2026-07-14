import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.app import MainWindow
from aix_host_app.widgets.active_dashboard import ActiveVisionDashboard


class ActiveVisionDashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_switches_between_display_and_diagnostic_modes(self):
        dashboard = ActiveVisionDashboard()
        self.assertTrue(dashboard.diagnostics.isHidden())
        dashboard.set_diagnostic_mode(True)
        self.assertFalse(dashboard.diagnostics.isHidden())
        self.assertEqual(dashboard.diagnostics.count(), 4)
        dashboard.set_diagnostic_mode(False)
        self.assertTrue(dashboard.diagnostics.isHidden())

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
        self.assertGreaterEqual(dashboard.decision_panel.minimumWidth(), 360)

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

        self.assertEqual(dashboard.instrument_subtitle.text(), "主动视觉闭环监控")
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
        self.assertTrue(hasattr(window, "chain_client"))
        self.assertFalse(hasattr(window, "vision_client"))
        self.assertGreaterEqual(window.minimumWidth(), 1280)
        self.assertGreaterEqual(window.minimumHeight(), 720)
        window.resize(1280, 720)
        window.show()
        self.app.processEvents()
        self.assertTrue(window.dashboard.risk_trend.isHidden())
        window.resize(1440, 900)
        self.app.processEvents()
        self.assertFalse(window.dashboard.risk_trend.isHidden())
        window.close()

    def test_compact_height_prioritizes_core_closed_loop_information(self):
        dashboard = ActiveVisionDashboard()
        dashboard.set_compact_mode(True)
        self.assertTrue(dashboard.risk_trend.isHidden())
        self.assertTrue(dashboard.safety_note.isHidden())

        dashboard.set_compact_mode(False)
        self.assertFalse(dashboard.risk_trend.isHidden())
        self.assertFalse(dashboard.safety_note.isHidden())
        dashboard.close()


if __name__ == "__main__":
    unittest.main()
