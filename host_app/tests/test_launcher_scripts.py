from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOST_APP = ROOT / "host_app"


class LauncherScriptTests(unittest.TestCase):
    def test_launcher_ensures_hotspot_before_starting_host_app(self):
        launcher = (HOST_APP / "start_stack.ps1").read_text(encoding="utf-8")
        helper_call = "ensure_mobile_hotspot.ps1"
        app_call = '"-m", "aix_host_app"'

        self.assertIn(helper_call, launcher)
        self.assertLess(launcher.index(helper_call), launcher.index(app_call))

    def test_launcher_uses_windows_powershell_for_winrt_hotspot_helper(self):
        launcher = (HOST_APP / "start_stack.ps1").read_text(encoding="utf-8")

        self.assertIn("powershell.exe", launcher)
        self.assertIn("-NoProfile", launcher)
        self.assertIn("-ExecutionPolicy", launcher)
        self.assertIn("-File", launcher)

    def test_hotspot_helper_uses_runtime_config_winrt_and_24ghz(self):
        helper = (HOST_APP / "ensure_mobile_hotspot.ps1").read_text(encoding="utf-8")

        self.assertIn("sdkconfig.runtime", helper)
        self.assertIn("NetworkOperatorTetheringManager", helper)
        self.assertIn("StartTetheringAsync", helper)
        self.assertIn("wifi_hotspot_ready", helper)
        self.assertIn("TwoPointFourGigahertz", helper)

    def test_launcher_syncs_runtime_then_starts_model_and_waits_for_health(self):
        launcher = (HOST_APP / "start_stack.ps1").read_text(encoding="utf-8")
        sync_script = ROOT / "AIX" / "sync_runtime_config.ps1"

        self.assertIn("sync_runtime_config.ps1", launcher)
        self.assertIn("server:create_runtime_app", launcher)
        self.assertIn("/healthz", launcher)
        self.assertLess(launcher.index("sync_runtime_config.ps1"), launcher.index("server:create_runtime_app"))
        self.assertLess(launcher.index("/healthz"), launcher.index('"-m", "aix_host_app"'))
        self.assertTrue(sync_script.exists())
        content = sync_script.read_text(encoding="utf-8")
        self.assertIn("CONFIG_AIX_WIFI_SSID", content)
        self.assertIn("CONFIG_AIX_LINK_TOKEN", content)


if __name__ == "__main__":
    unittest.main()
