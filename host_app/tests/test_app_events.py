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

    def test_routes_vision_depth_to_visual_panel(self):
        window = MainWindow()
        window._handle_raw_line(
            '{"type":"vision_depth","version":1,"frame_seq":7,"capture_ts_ms":1200,'
            '"model":"DA3-SMALL","depth_kind":"relative","depth_p10":0.42,'
            '"depth_median":1.37,"confidence_median":0.86,"latency_ms":74.5,"valid":true}'
        )

        self.assertIn("DA3-SMALL", window.vision_panel.detect_label.text())
        self.assertIn("1.37", window.vision_panel.detect_label.text())

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

    def test_routes_preview_url_to_vision_panel(self):
        window = MainWindow()

        window._handle_raw_line(
            '{"type":"camera_preview","version":1,"valid":true,'
            '"url":"http://192.168.137.23:8080/capture.jpg",'
            '"ip":"192.168.137.23","port":8080,"reason":"ready"}'
        )

        self.assertEqual(window.vision_panel.preview_url, "http://192.168.137.23:8080/capture.jpg")

    def test_updates_pc_risk_and_dominant_object(self):
        window = MainWindow()

        window._accept_vision_result({
            "type": "vision_risk",
            "frame_seq": 8,
            "capture_ts_ms": 1300,
            "depth_p10": 0.2,
            "depth_median": 0.7,
            "confidence_median": 0.9,
            "detections": [{
                "class_name": "car", "score": 0.9,
                "bbox_norm": [0.2, 0.3, 0.8, 0.9],
                "relative_depth": 0.2, "risk_score": 72.0,
            }],
            "risk_score": 72,
            "risk_band": "high",
            "dominant_class": "car",
            "reason": "car_approaching",
            "latency_ms": 85.0,
            "valid": True,
        })

        self.assertIn("72", window.vision_panel.risk_label.text())
        self.assertIn("car", window.vision_panel.detect_label.text())
        self.assertEqual(window.overview_panel.risk.value.text(), "72")


if __name__ == "__main__":
    unittest.main()
