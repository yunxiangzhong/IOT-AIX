import unittest

from aix_host_app.models import ActionStatusEvent, CameraPreviewEvent, CameraStatusEvent, HardwareHealthEvent, MotionEvent, PneumaticStatusEvent, PressureSample, RiskAckEvent, RoadHazardStatusEvent, VisionDepthEvent, VoiceStatusEvent
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

    def test_parses_motion_v2_acceleration_and_event_diagnostics(self):
        event = parse_event_line(
            '{"type":"motion","version":2,"seq":2,"ts_ms":1000,'
            '"accel_g":{"x":0.1,"y":0.2,"z":0.97},'
            '"gyro_dps":{"x":1.0,"y":2.0,"z":3.0},'
            '"accel_norm_g":1.0,"tilt_deg":12.3,"impact":false,'
            '"rapid_tilt":true,"danger_latched":true,"calibrated":true,'
            '"speed_mps":0.0,"speed_valid":false}'
        )
        self.assertTrue(event.rapid_tilt)
        self.assertAlmostEqual(event.accel_norm_g, 1.0)
        self.assertFalse(event.speed_valid)


class HardwareHealthParserTests(unittest.TestCase):
    def test_parses_real_module_health_heartbeat(self):
        event = parse_event_line(
            '{"type":"hardware_health","version":1,"ts_ms":1000,'
            '"overall":"degraded","automatic_ready":false,'
            '"ov5640":"healthy","mpu6050":"healthy","pressure":"healthy",'
            '"dfplayer":"healthy","rgb":"healthy","pump":"pending","valve":"pending",'
            '"reason":"awaiting_pneumatic_self_test"}'
        )
        self.assertIsInstance(event, HardwareHealthEvent)
        self.assertEqual(event.modules["ov5640"], "healthy")
        self.assertFalse(event.automatic_ready)
        self.assertEqual(event.reason, "awaiting_pneumatic_self_test")


class PneumaticStatusParserTests(unittest.TestCase):
    def test_parses_pneumatic_status(self):
        event = parse_event_line(
            '{"type":"pneumatic_status","version":1,"ts_ms":1000,'
            '"state":"holding","fault":"none","trigger":"vision_high",'
            '"operation":1,"pump_on":false,"valve_on":true,'
            '"pressure_kpa":2.1,"pressure_valid":true,"pressure_age_ms":20,'
            '"pump_verified":true,"valve_verified":true,"self_test_failed":false,'
            '"vision_state":"high","vision_fresh":true,"mpu_available":true,'
            '"mpu_calibrated":true,"impact":false,"rapid_tilt":false}'
        )
        self.assertIsInstance(event, PneumaticStatusEvent)
        self.assertEqual(event.state, "holding")
        self.assertTrue(event.valve_on)
        self.assertTrue(event.pump_verified)
        self.assertTrue(event.valve_verified)
        self.assertFalse(event.self_test_failed)


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


class CameraPreviewParserTests(unittest.TestCase):
    def test_parses_camera_preview_event(self):
        event = parse_event_line(
            '{"type":"camera_preview","version":1,"valid":true,'
            '"url":"http://192.168.137.23:8080/capture.jpg",'
            '"ip":"192.168.137.23","port":8080,"reason":"ready"}'
        )
        self.assertIsInstance(event, CameraPreviewEvent)
        self.assertEqual(event.port, 8080)
        self.assertTrue(event.url.endswith("/capture.jpg"))

    def test_rejects_camera_preview_with_missing_url(self):
        with self.assertRaises(ParseError):
            parse_event_line(
                '{"type":"camera_preview","version":1,"valid":true,'
                '"ip":"192.168.137.23","port":8080,"reason":"ready"}'
            )


class VisionDepthParserTests(unittest.TestCase):
    def test_parses_relative_depth_event(self):
        event = parse_event_line(
            '{"type":"vision_depth","version":1,"frame_seq":7,"capture_ts_ms":1200,'
            '"model":"DA3-SMALL","depth_kind":"relative","depth_p10":0.42,'
            '"depth_median":1.37,"confidence_median":0.86,"latency_ms":74.5,"valid":true}'
        )
        self.assertIsInstance(event, VisionDepthEvent)
        self.assertEqual(event.frame_seq, 7)
        self.assertEqual(event.depth_kind, "relative")

    def test_rejects_vision_depth_with_missing_fields(self):
        with self.assertRaises(ParseError):
            parse_event_line('{"type":"vision_depth","version":1,"frame_seq":1}')


class RiskAckParserTests(unittest.TestCase):
    def test_parses_risk_ack_event(self):
        event = parse_event_line(
            '{"type":"risk_ack","version":1,"frame_seq":12,"risk_score":68,'
            '"risk_band":"high","valid":true,"stale":false}'
        )

        self.assertIsInstance(event, RiskAckEvent)
        self.assertEqual(event.risk_score, 68)

    def test_rejects_risk_ack_outside_score_range(self):
        with self.assertRaises(ParseError):
            parse_event_line(
                '{"type":"risk_ack","version":1,"frame_seq":12,"risk_score":101,'
                '"risk_band":"critical","valid":true,"stale":false}'
            )


class ActionStatusParserTests(unittest.TestCase):
    def test_parses_action_status_heartbeat(self):
        event = parse_event_line(
            '{"type":"action_status","version":1,"ts_ms":4200,"frame_seq":17,'
            '"risk_score":71,"valid":true,"stale":false,'
            '"action_state":"high","rgb_pattern":"orange_blink_2hz"}'
        )

        self.assertIsInstance(event, ActionStatusEvent)
        self.assertEqual(event.frame_seq, 17)
        self.assertEqual(event.rgb_pattern, "orange_blink_2hz")


class CooperativeSerialParserTests(unittest.TestCase):
    def test_parses_real_firmware_road_hazard_status_without_severity(self):
        event = parse_event_line(
            '{"type":"road_hazard_status","version":1,"state":"active",'
            '"event_id":"demo-truck-right-5s","reason":"",'
            '"expires_in_ms":6500,"effective_rgb_pattern":"orange_blink_2hz"}'
        )
        self.assertIsInstance(event, RoadHazardStatusEvent)
        self.assertEqual(event.severity, "unknown")
        self.assertEqual(event.state, "active")

    def test_parses_voice_status_lifecycle(self):
        event = parse_event_line(
            '{"type":"voice_status","version":1,"state":"finished",'
            '"track":2,"frame_seq":18,"command_id":"risk-18","error":""}'
        )
        self.assertIsInstance(event, VoiceStatusEvent)
        self.assertEqual(event.track, 2)


if __name__ == "__main__":
    unittest.main()
