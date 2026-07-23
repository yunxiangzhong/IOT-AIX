import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

from operating_mode import OperatingModeController


class OperatingModeTests(unittest.TestCase):
    def test_demo_lease_pauses_real_dispatch_and_expiry_restores_real(self):
        now = [1_000]
        mode = OperatingModeController(clock_ms=lambda: now[0])
        self.assertEqual(mode.snapshot()["mode"], "real")

        started = mode.start("demo-1", lease_ms=15_000)
        self.assertTrue(started["accepted"])
        self.assertEqual(mode.snapshot()["mode"], "demo")
        self.assertFalse(mode.is_real())

        heartbeat = mode.heartbeat("demo-1", lease_ms=15_000, now_ms=10_000)
        self.assertTrue(heartbeat["accepted"])
        self.assertEqual(heartbeat["lease_remaining_ms"], 15_000)

        now[0] = 25_001
        self.assertTrue(mode.is_real())
        self.assertEqual(mode.snapshot()["reason"], "lease_expired")

    def test_wrong_session_cannot_heartbeat_or_end_demo(self):
        mode = OperatingModeController(clock_ms=lambda: 1_000)
        mode.start("demo-1", lease_ms=15_000)
        self.assertFalse(mode.heartbeat("other", lease_ms=15_000)["accepted"])
        self.assertFalse(mode.end("other")["accepted"])
        self.assertEqual(mode.snapshot()["mode"], "demo")


if __name__ == "__main__":
    unittest.main()
