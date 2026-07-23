from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HOST_APP = ROOT / "host_app"


class LauncherScriptTests(unittest.TestCase):
    def test_launcher_ensures_hotspot_before_starting_host_app(self):
        launcher = (HOST_APP / "start_stack.ps1").read_text(encoding="utf-8")
        helper_call = "ensure_mobile_hotspot.ps1"
        app_call = '"-m", "aix_host_app.web_server"'

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
        self.assertLess(launcher.index("/healthz"), launcher.index('"-m", "aix_host_app.web_server"'))
        self.assertTrue(sync_script.exists())
        content = sync_script.read_text(encoding="utf-8")
        self.assertIn("CONFIG_AIX_WIFI_SSID", content)
        self.assertIn("CONFIG_AIX_LINK_TOKEN", content)
        self.assertIn('ValidateSet("Preserve", "Manual", "Automatic")', content)
        self.assertIn("CONFIG_AIX_ENABLE_PNEUMATIC_AUTOMATIC", content)

    def test_launcher_starts_loopback_browser_dashboard_on_9696(self):
        launcher = (HOST_APP / "start_stack.ps1").read_text(encoding="utf-8")
        command = (HOST_APP / "start_host_app.cmd").read_text(encoding="utf-8")

        self.assertIn("127.0.0.1:$WebPort", launcher)
        self.assertIn("aix_host_app.web_server", launcher)
        self.assertIn('set "AIX_WEB_PORT=9696"', command)

    def test_launcher_reuses_only_the_expected_ready_cuda_model_service(self):
        launcher = (HOST_APP / "start_stack.ps1").read_text(encoding="utf-8")

        self.assertIn("function Test-RealModelHealth", launcher)
        for marker in (
            "model_ready", "model_state", "DA3-SMALL", "YOLO26m-COCO", "cuda",
            "tensorrt-fp16", "pytorch-cuda-fp16",
        ):
            self.assertIn(marker, launcher)
        self.assertGreaterEqual(launcher.count("Test-RealModelHealth"), 3)
        self.assertNotIn("$reuseHealthyService = $existingHealth.http_ready -eq $true", launcher)
        self.assertNotIn("if ($health.http_ready -eq $true)", launcher)


if __name__ == "__main__":
    unittest.main()
