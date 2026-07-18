import json
import tempfile
import unittest
from pathlib import Path

from aix_host_app.session_recorder import SessionRecorder


class SessionRecorderTests(unittest.TestCase):
    def test_creates_session_and_writes_frame_telemetry_and_risk(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = SessionRecorder(Path(temp_dir))
            session = recorder.start("COM21", 115200, "session-1")
            frame_path = recorder.save_frame(b"\xff\xd8frame\xff\xd9", 7, 1234)
            recorder.record_event('{"type":"pressure","valid":true}')
            recorder.record_vision({"type": "vision_risk", "risk_score": 42})
            recorder.record_action({"type": "action_status", "frame_seq": 7, "action_state": "attention", "rgb_pattern": "yellow_blink_1hz", "stale": False})
            recorder.record_action({"type": "action_status", "frame_seq": 7, "action_state": "attention", "rgb_pattern": "yellow_blink_1hz", "stale": False})
            recorder.record_pneumatic({"type": "pneumatic_status", "state": "vented"})
            recorder.record_pneumatic_config({"type": "pneumatic_config", "target_kpa": 2.0})
            recorder.record_road_hazard({"type": "road_hazard_status", "state": "active", "event_id": "demo-truck-right-5s"})
            duplicate_path = recorder.save_frame(b"different", 7, 1234)
            recorder.append_model_log("model ready")
            recorder.close()

            self.assertTrue((session / "session.json").exists())
            self.assertTrue(frame_path.exists())
            self.assertEqual(frame_path.read_bytes(), b"\xff\xd8frame\xff\xd9")
            self.assertEqual(duplicate_path, frame_path)
            self.assertIn("pressure", (session / "telemetry.ndjson").read_text(encoding="utf-8"))
            self.assertIn("vision_risk", (session / "vision.ndjson").read_text(encoding="utf-8"))
            self.assertEqual((session / "action.ndjson").read_text(encoding="utf-8").count("action_status"), 1)
            self.assertIn("pneumatic_status", (session / "pneumatic.ndjson").read_text(encoding="utf-8"))
            self.assertIn("demo-truck-right-5s", (session / "road_hazard.ndjson").read_text(encoding="utf-8"))
            self.assertIn("model ready", (session / "model.log").read_text(encoding="utf-8"))
            metadata = json.loads((session / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["serial_port"], "COM21")
            self.assertEqual(metadata["pneumatic_config"]["target_kpa"], 2.0)
            self.assertIsNotNone(metadata["ended_at"])


if __name__ == "__main__":
    unittest.main()
