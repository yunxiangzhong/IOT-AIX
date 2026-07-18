import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from aix_host_app.app import MainWindow
from aix_host_app.models import RoadHazardStatusEvent, VoiceStatusEvent
from aix_host_app.widgets.cooperative_scenario import CooperativeScenarioPanel


class CooperativeWarningUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_main_window_uses_two_primary_pages_and_light_apple_surface(self):
        window = MainWindow()
        self.assertIsInstance(window.primary_pages, QtWidgets.QStackedWidget)
        self.assertEqual(window.primary_pages.count(), 2)
        self.assertEqual(window.overview_button.text(), "中控总览")
        self.assertEqual(window.scenario_button.text(), "协同场景")
        self.assertIn("#F5F5F7", window.styleSheet())
        window._show_scenario()
        self.assertEqual(window.primary_pages.currentIndex(), 1)
        window._show_overview()
        self.assertEqual(window.primary_pages.currentIndex(), 0)
        self.assertEqual(window._page_fade.duration(), 200)
        window._set_reduce_motion(True)
        self.assertTrue(window.reduce_motion_check.isChecked())
        window.close()

    def test_overview_exposes_6112_columns_and_stale_does_not_make_new_execution(self):
        window = MainWindow()
        overview = window.dashboard
        self.assertEqual(overview.workspace_ratios, (6, 1, 1, 2))
        self.assertEqual(overview.peripheral_panel.objectName(), "peripheralPanel")
        self.assertEqual(overview.realtime_panel.objectName(), "realtimePanel")
        self.assertIn("尚未完成气囊实物验收", overview.pneumatic_acceptance_note.text())
        state = {
            "device_id": "aix-helmet-01", "boot_id": "0123456789abcdef",
            "upload": {"state": "healthy", "last_frame_seq": 2, "fps": 1.0, "frame_age_ms": 40},
            "model": {"state": "ready", "latency_ms": 80.0, "gpu": "cuda"},
            "callback": {"state": "confirmed", "latency_ms": 10.0},
            "risk": {"valid": True, "score": 75, "band": "high", "reason": "scene_proximity", "frame_seq": 2},
            "action": {"confirmed": True, "state": "high", "rgb_pattern": "orange_blink_2hz", "frame_seq": 2, "stale": False},
            "last_error": "",
        }
        overview.apply_chain_state(state)
        self.assertIn("高风险", overview.action_name.text())
        stale = {**state, "upload": {**state["upload"], "frame_age_ms": 4100},
                 "risk": {**state["risk"], "valid": False},
                 "action": {**state["action"], "state": "fault", "stale": True}}
        overview.apply_chain_state(stale)
        self.assertIn("不生成", overview.execution_guard.text())
        self.assertIn("失效", overview.risk_band.text())
        window.close()

    def test_voice_and_serial_road_hazard_status_have_explicit_safe_copy(self):
        window = MainWindow()
        overview = window.dashboard
        overview.apply_voice_status(VoiceStatusEvent("playing", "road-risk-7", 2, ""))
        self.assertIn("播放中", overview.voice_status_value.text())
        overview.apply_voice_status(VoiceStatusEvent("error", "road-risk-7", 2, "tf_card_not_ready"))
        self.assertIn("错误", overview.voice_status_value.text())
        window._accept_road_hazard_status(RoadHazardStatusEvent("active", "demo-truck-right-5s", "high", "orange_blink_2hz", ""))
        self.assertIn("专用语音未配置", window.scenario_panel.voice_value.text())
        self.assertIn("active", window.scenario_panel.serial_status.text())
        window.close()

    def test_scene_final_stage_requires_actual_ack_and_reset_reenables_start(self):
        scene = CooperativeScenarioPanel()
        scene.begin_demo()
        self.assertFalse(scene.start_button.isEnabled())
        self.assertNotIn("已确认", scene.stages[-1].meta.text())
        scene.apply_chain_state({"road_hazard": {
            "event_id": "demo-truck-right-5s", "roadside_capture": {"state": "completed"},
            "cloud_recognition": {"state": "completed"}, "arrival_prediction": {"state": "completed"},
            "delivery": {"state": "completed"}, "ack": {"state": "completed", "payload": None},
            "network_latency_ms": 32, "effective_rgb_pattern": "orange_blink_2hz", "error": "",
        }})
        self.assertIn("等待真实 ACK", scene.stages[-1].meta.text())
        scene.apply_chain_state({"road_hazard": {
            "event_id": "demo-truck-right-5s", "roadside_capture": {"state": "completed"},
            "cloud_recognition": {"state": "completed"}, "arrival_prediction": {"state": "completed"},
            "delivery": {"state": "completed"}, "ack": {"state": "completed", "payload": {"type": "road_hazard_ack", "accepted": True, "event_id": "demo-truck-right-5s"}},
            "network_latency_ms": 32, "effective_rgb_pattern": "orange_blink_2hz", "error": "",
        }})
        self.assertIn("真实 ACK", scene.stages[-1].meta.text())
        scene.reset_demo()
        self.assertTrue(scene.start_button.isEnabled())

    def test_scene_failure_stops_at_retry_or_failed_not_success(self):
        scene = CooperativeScenarioPanel()
        scene.begin_demo()
        scene.apply_chain_state({"road_hazard": {
            "event_id": "demo-truck-right-5s", "delivery": {"state": "failed"},
            "ack": {"state": "failed", "payload": None}, "attempts": 4,
            "network_latency_ms": None, "effective_rgb_pattern": "", "error": "no recent frame for device",
        }})
        self.assertIn("失败", scene.stages[3].meta.text())
        self.assertIn("未确认", scene.stages[-1].meta.text())

    def test_core_layout_remains_available_at_1440x900_and_1280x720(self):
        window = MainWindow()
        for width, height in ((1440, 900), (1280, 720)):
            window.resize(width, height)
            window.show()
            self.app.processEvents()
            self.assertTrue(window.dashboard.camera_image.isVisible())
            self.assertTrue(window.dashboard.peripheral_panel.isVisible())
            self.assertTrue(window.dashboard.realtime_panel.isVisible())
            self.assertTrue(window.dashboard.decision_panel.isVisible())
        window.close()


if __name__ == "__main__":
    unittest.main()
