import json
import unittest

from aix_host_app.config_events import make_pressure_config_line


class ConfigEventTests(unittest.TestCase):
    def test_makes_pressure_disabled_config_line(self):
        payload = json.loads(make_pressure_config_line(False))

        self.assertEqual(payload["type"], "config")
        self.assertEqual(payload["version"], 1)
        self.assertFalse(payload["pressure_enabled"])

    def test_makes_pressure_enabled_config_line(self):
        payload = json.loads(make_pressure_config_line(True))

        self.assertTrue(payload["pressure_enabled"])


if __name__ == "__main__":
    unittest.main()
