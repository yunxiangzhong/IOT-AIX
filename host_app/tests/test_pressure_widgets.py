import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.models import PressureSample
from aix_host_app.widgets.pressure_panel import PressurePanel
from aix_host_app.widgets.sensor_overview_panel import SensorOverviewPanel


class InvalidPressureWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_invalid_pressure_is_diagnostic_only(self):
        panel = PressurePanel()
        panel.update_sample(PressureSample(0, 0, 1200, 900, 56.0, 56.0, False, True))
        panel.update_sample(PressureSample(1, 1, 0, 0, 0.0, 0.4, False, False))

        self.assertEqual(panel.value_label.text(), "— kPa")
        self.assertIn("0 mV", panel.detail_label.text())
        self.assertIsNone(panel.history.latest())

    def test_overview_hides_invalid_pressure_value(self):
        panel = SensorOverviewPanel()
        panel.update_pressure(PressureSample(1, 1, 0, 0, 0.0, 0.4, False, False))

        self.assertEqual(panel.pressure.value.text(), "— kPa")
        self.assertIn("电压异常", panel.pressure.status.text())


if __name__ == "__main__":
    unittest.main()
