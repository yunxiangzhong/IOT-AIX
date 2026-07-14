from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOST_APP = ROOT / "host_app"


class LauncherScriptTests(unittest.TestCase):
    def test_launcher_ensures_hotspot_before_starting_host_app(self):
        launcher = (HOST_APP / "start_host_app.cmd").read_text(encoding="utf-8")
        helper_call = "ensure_mobile_hotspot.ps1"
        app_call = '"%PYTHON%" -m aix_host_app'

        self.assertIn(helper_call, launcher)
        self.assertLess(launcher.index(helper_call), launcher.index(app_call))

    def test_hotspot_helper_uses_preview_config_and_winrt_tethering(self):
        helper = (HOST_APP / "ensure_mobile_hotspot.ps1").read_text(encoding="utf-8")

        self.assertIn("sdkconfig.preview", helper)
        self.assertIn("NetworkOperatorTetheringManager", helper)
        self.assertIn("StartTetheringAsync", helper)
        self.assertIn("wifi_hotspot_ready", helper)

    def test_launcher_syncs_preview_credentials_into_active_sdkconfig(self):
        launcher = (HOST_APP / "start_host_app.cmd").read_text(encoding="utf-8")
        sync_script = (ROOT / "AIX" / "sync_preview_sdkconfig.ps1")

        self.assertIn("sync_preview_sdkconfig.ps1", launcher)
        self.assertTrue(sync_script.exists())
        content = sync_script.read_text(encoding="utf-8")
        self.assertIn("CONFIG_AIX_WIFI_SSID", content)
        self.assertIn("CONFIG_AIX_WIFI_PASSWORD", content)


if __name__ == "__main__":
    unittest.main()
