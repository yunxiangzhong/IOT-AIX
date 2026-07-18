import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class FirmwareTimingDefaultsTests(unittest.TestCase):
    def test_all_firmware_upload_defaults_are_one_second(self):
        sdkconfig = (PROJECT_ROOT / "AIX" / "sdkconfig.defaults").read_text(encoding="utf-8")
        runtime_path = PROJECT_ROOT / "AIX" / "sdkconfig.runtime"
        sync_script = (PROJECT_ROOT / "AIX" / "sync_runtime_config.ps1").read_text(encoding="utf-8")
        kconfig = (PROJECT_ROOT / "AIX" / "main" / "Kconfig.projbuild").read_text(encoding="utf-8")
        uplink = (PROJECT_ROOT / "AIX" / "main" / "vision_uplink.c").read_text(encoding="utf-8")

        self.assertIn("CONFIG_AIX_VISION_UPLOAD_PERIOD_MS=1000", sdkconfig)
        self.assertIn('CONFIG_AIX_VISION_UPLOAD_PERIOD_MS = "1000"', sync_script)
        self.assertRegex(kconfig, r"(?s)config AIX_VISION_UPLOAD_PERIOD_MS\s+int.*?default 1000")
        self.assertIn("#define CONFIG_AIX_VISION_UPLOAD_PERIOD_MS 1000", uplink)
        if runtime_path.exists():
            runtime = runtime_path.read_text(encoding="utf-8")
            self.assertIn("CONFIG_AIX_VISION_UPLOAD_PERIOD_MS=1000", runtime)


if __name__ == "__main__":
    unittest.main()
