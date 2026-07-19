import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.widgets.connection_panel import ConnectionPanel


class ConnectionPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_pressure_monitoring_switch_is_not_exposed(self):
        panel = ConnectionPanel()

        self.assertFalse(hasattr(panel, "pressure_monitoring_check"))
        self.assertFalse(hasattr(panel, "pressure_state_label"))

    def test_device_sheet_excludes_session_and_display_preferences(self):
        panel = ConnectionPanel()
        self.assertFalse(hasattr(panel, "storage_root_edit"))
        self.assertFalse(hasattr(panel, "recording_check"))
        self.assertFalse(hasattr(panel, "reduce_motion_check"))
        self.assertFalse(hasattr(panel, "source_combo"))
        self.assertGreaterEqual(panel.minimumWidth(), 420)


if __name__ == "__main__":
    unittest.main()
