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
            recorder.close()

            self.assertTrue((session / "session.json").exists())
            self.assertTrue(frame_path.exists())
            self.assertEqual(frame_path.read_bytes(), b"\xff\xd8frame\xff\xd9")
            self.assertIn("pressure", (session / "telemetry.ndjson").read_text(encoding="utf-8"))
            self.assertIn("vision_risk", (session / "vision.ndjson").read_text(encoding="utf-8"))
            metadata = json.loads((session / "session.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["serial_port"], "COM21")
            self.assertIsNotNone(metadata["ended_at"])


if __name__ == "__main__":
    unittest.main()
