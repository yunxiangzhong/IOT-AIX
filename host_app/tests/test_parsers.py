import unittest

from aix_host_app.models import PressureSample
from aix_host_app.parsers import ParseError, parse_pressure_line


class PressureParserTests(unittest.TestCase):
    def test_parses_pressure_ndjson_line(self):
        line = (
            '{"type":"pressure","version":1,"seq":123,"ts_ms":45678,'
            '"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,'
            '"over_pressure":false,"valid":true}'
        )

        sample = parse_pressure_line(line)

        self.assertIsInstance(sample, PressureSample)
        self.assertEqual(sample.seq, 123)
        self.assertEqual(sample.ts_ms, 45678)
        self.assertEqual(sample.raw, 2048)
        self.assertEqual(sample.mv, 1450)
        self.assertAlmostEqual(sample.kpa, 100.0)
        self.assertAlmostEqual(sample.filtered_kpa, 98.4)
        self.assertFalse(sample.over_pressure)
        self.assertTrue(sample.valid)
        self.assertEqual(sample.source, "json")

    def test_parses_legacy_pressure_log_line(self):
        line = "I (1234) AIX_PRESSURE: PRESSURE,seq=9,raw=2000,mv=1400,kpa=96.00,filtered=91.50,over=0,valid=1"

        sample = parse_pressure_line(line)

        self.assertEqual(sample.seq, 9)
        self.assertEqual(sample.ts_ms, 1234)
        self.assertEqual(sample.raw, 2000)
        self.assertEqual(sample.mv, 1400)
        self.assertAlmostEqual(sample.kpa, 96.0)
        self.assertAlmostEqual(sample.filtered_kpa, 91.5)
        self.assertFalse(sample.over_pressure)
        self.assertTrue(sample.valid)
        self.assertEqual(sample.source, "legacy")

    def test_rejects_non_pressure_json_event(self):
        with self.assertRaises(ParseError):
            parse_pressure_line('{"type":"vision","version":1}')

    def test_rejects_missing_required_json_field(self):
        with self.assertRaises(ParseError):
            parse_pressure_line('{"type":"pressure","version":1,"seq":1}')

    def test_rejects_malformed_line(self):
        with self.assertRaises(ParseError):
            parse_pressure_line("boot log without pressure data")


if __name__ == "__main__":
    unittest.main()
