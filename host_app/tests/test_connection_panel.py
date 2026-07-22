import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.serial_source import SerialPortOption
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

    def test_manual_port_without_usb_identity_can_be_selected(self):
        panel = ConnectionPanel()
        panel.set_ports([SerialPortOption("COM7", "USB-SERIAL CH340")])

        self.assertEqual(panel.current_port(), "COM7")
        self.assertTrue(panel.connect_button.isEnabled())

    def test_matching_port_is_preselected_but_all_ports_remain_available(self):
        panel = ConnectionPanel()
        panel.set_ports([
            SerialPortOption("COM8", "蓝牙链接上的标准串行"),
            SerialPortOption("COM21", "Silicon Labs CP210x USB to UART Bridge"),
        ], preferred_device="COM21")

        self.assertEqual(panel.current_port(), "COM21")
        self.assertEqual(panel.port_combo.count(), 2)
        self.assertIn("手动切换", panel.detail_label.text())

    def test_bluetooth_ports_are_not_selected_when_no_target_is_recognized(self):
        panel = ConnectionPanel()
        panel.set_ports([
            SerialPortOption("COM8", "蓝牙链接上的标准串行"),
            SerialPortOption("COM12", "蓝牙链接上的标准串行"),
        ])

        self.assertEqual(panel.current_port(), "")
        self.assertEqual(panel.port_combo.currentIndex(), -1)


if __name__ == "__main__":
    unittest.main()
