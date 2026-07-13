import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtWidgets

from aix_host_app.app import MainWindow


class MainWindowEventRoutingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_routes_camera_status_to_vision_panel(self):
        window = MainWindow()
        window.vision_panel.set_serial_connected(True)

        window._handle_raw_line(
            '{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,'
            '"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg",'
            '"frame_bytes":18432,"fps":5.0,"frames_ok":12,"capture_failures":0,'
            '"psram":false,"valid":true}'
        )

        self.assertIn("分辨率：320×240", window.vision_panel.camera_detail_label.text())

    def test_valid_camera_status_marks_ov5640_as_normal(self):
        window = MainWindow()
        window.vision_panel.set_serial_connected(True)

        window._handle_raw_line(
            '{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,'
            '"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg",'
            '"frame_bytes":18432,"fps":5.0,"frames_ok":12,"capture_failures":0,'
            '"psram":false,"valid":true}'
        )

        self.assertEqual(window.vision_panel.camera_status_button.text(), "OV5640：状态正常")

    def test_camera_status_timeout_marks_ov5640_as_abnormal(self):
        window = MainWindow()
        window.vision_panel.set_serial_connected(True)
        window.vision_panel.camera_status_timer.timeout.emit()

        self.assertEqual(window.vision_panel.camera_status_button.text(), "OV5640：连接异常")

    def test_camera_details_toggle_without_changing_status(self):
        window = MainWindow()
        self.assertTrue(window.vision_panel.camera_details.isHidden())

        window.vision_panel.camera_status_button.click()
        self.assertFalse(window.vision_panel.camera_details.isHidden())
        self.assertEqual(window.vision_panel.camera_status_button.text(), "OV5640：等待状态")

        window.vision_panel.camera_status_button.click()
        self.assertTrue(window.vision_panel.camera_details.isHidden())


if __name__ == "__main__":
    unittest.main()
