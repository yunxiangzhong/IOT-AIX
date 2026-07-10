import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.app import MainWindow


class MainWindowEventRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_routes_voice_event_to_timeline(self):
        window = MainWindow()

        window._handle_raw_line(
            '{"type":"voice","version":1,"seq":9,"ts_ms":1200,'
            '"text":"前方车辆接近","played":true}'
        )

        log_text = window.timeline.log.toPlainText()
        self.assertIn("voice", log_text)
        self.assertIn("前方车辆接近", log_text)
        self.assertIn("voice 9", window.timeline.summary.text())


if __name__ == "__main__":
    unittest.main()
