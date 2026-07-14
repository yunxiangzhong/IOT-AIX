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
        self.assertIn("ORANGE", dashboard.action_pattern.text())

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
        self.assertIn("PURPLE", dashboard.action_pattern.text())

    def test_main_window_uses_pc_chain_client_and_minimum_dashboard_size(self):
        window = MainWindow()
        self.assertTrue(hasattr(window, "chain_client"))
        self.assertFalse(hasattr(window, "vision_client"))
        self.assertGreaterEqual(window.minimumWidth(), 1280)
        self.assertGreaterEqual(window.minimumHeight(), 720)
        window.close()


if __name__ == "__main__":
    unittest.main()
