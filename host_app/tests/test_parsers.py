import unittest

from aix_host_app.models import CameraStatusEvent, MotionEvent, PressureSample
from aix_host_app.parsers import ParseError, parse_event_line, parse_pressure_line


class PressureParserTests(unittest.TestCase):
    def test_parses_pressure_ndjson_line(self):
        sample = parse_pressure_line(
            '{"type":"pressure","version":1,"seq":123,"ts_ms":45678,'
            '"raw":2048,"mv":1450,"kpa":100.0,"filtered_kpa":98.4,'
            '"over_pressure":false,"valid":true}'
        )
        self.assertIsInstance(sample, PressureSample)
        self.assertEqual(sample.seq, 123)
        self.assertTrue(sample.valid)

    def test_parses_legacy_pressure_log_line(self):
        sample = parse_pressure_line(
            "I (1234) AIX_PRESSURE: PRESSURE,seq=9,raw=2000,mv=1400,kpa=96.00,filtered=91.50,over=0,valid=1"
        )
        self.assertEqual(sample.source, "legacy")
        self.assertEqual(sample.ts_ms, 1234)

class MotionParserTests(unittest.TestCase):
    def test_keeps_motion_protocol_available(self):
        event = parse_event_line(
            '{"type":"motion","version":1,"seq":2,"ts_ms":1000,'
            '"speed_mps":4.5,"accel_mps2":0.2,"speed_valid":true,"accel_valid":true}'
        )
        self.assertIsInstance(event, MotionEvent)
        self.assertEqual(event.speed_mps, 4.5)


class CameraStatusParserTests(unittest.TestCase):
    def test_parses_camera_status_event(self):
        event = parse_event_line(
            '{"type":"camera_status","version":1,"seq":7,"ts_ms":1200,'
            '"sensor":"OV5640","width":320,"height":240,"pixel_format":"jpeg",'
            '"frame_bytes":18432,"fps":5.0,"frames_ok":12,"capture_failures":1,'
            '"psram":false,"valid":true}'
        )
        self.assertIsInstance(event, CameraStatusEvent)
        self.assertEqual((event.width, event.height), (320, 240))

    def test_rejects_camera_status_with_missing_fields(self):
        with self.assertRaises(ParseError):
            parse_event_line('{"type":"camera_status","version":1,"seq":1,"ts_ms":1000}')


if __name__ == "__main__":
    unittest.main()
