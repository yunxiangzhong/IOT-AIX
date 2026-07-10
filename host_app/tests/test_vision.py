import unittest

from aix_host_app.vision import CameraSourceConfig, NullVisionAnalyzer


class CameraSourceConfigTests(unittest.TestCase):
    def test_local_camera_value_is_parsed_as_device_index(self):
        config = CameraSourceConfig(kind="local", value="0")

        self.assertEqual(config.capture_input(), 0)
        self.assertEqual(config.source_label(), "本机摄像头 0")

    def test_url_camera_value_is_preserved(self):
        url = "http://192.168.1.20:8080/video"
        config = CameraSourceConfig(kind="url", value=url)

        self.assertEqual(config.capture_input(), url)
        self.assertEqual(config.source_label(), url)

    def test_invalid_local_camera_value_has_clear_error(self):
        config = CameraSourceConfig(kind="local", value="front")

        with self.assertRaisesRegex(ValueError, "本机摄像头编号必须是整数"):
            config.capture_input()


class NullVisionAnalyzerTests(unittest.TestCase):
    def test_default_result_keeps_risk_level_zero(self):
        result = NullVisionAnalyzer().analyze(None)

        self.assertEqual(result.scene, "实时画面")
        self.assertEqual(result.targets, "待接入算法")
        self.assertEqual(result.risk_level, 0)
        self.assertEqual(result.action, "保持")


if __name__ == "__main__":
    unittest.main()
