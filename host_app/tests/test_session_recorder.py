import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from aix_host_app.session_recorder import SessionRecorder


class SessionRecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_materializes_latest_processed_png_for_static_pc_preview(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image = QtGui.QImage(16, 12, QtGui.QImage.Format.Format_RGB32)
            image.fill(QtGui.QColor("#234567"))
            jpeg = QtCore.QBuffer()
            jpeg.open(QtCore.QIODevice.OpenModeFlag.WriteOnly)
            self.assertTrue(image.save(jpeg, "JPG"))

            recorder = SessionRecorder(Path(temp_dir))
            snapshot_path = recorder.save_png_snapshot(bytes(jpeg.data()))

            self.assertEqual(snapshot_path, Path(temp_dir) / "latest_processed.png")
            self.assertTrue(snapshot_path.exists())
            self.assertEqual(snapshot_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

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

    def test_records_collision_lifecycle_as_append_only_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = SessionRecorder(Path(temp_dir))
            recorder.record_collision({"event": "detected", "collision_id": "collision-1"})
            session = recorder.start("COM21", 115200, "session-1")

            recorder.record_collision({"event": "detected", "collision_id": "collision-1", "wall_time": "forged"})
            recorder.record_collision({"event": "pneumatic_update", "collision_id": "collision-1"})
            recorder.record_collision({"event": "acknowledged", "collision_id": "collision-1"})
            recorder.close()
            recorder.close()

            lines = (session / "collision_events.jsonl").read_text(encoding="utf-8").splitlines()
            events = [json.loads(line) for line in lines]

            self.assertEqual(len(events), 3)
            self.assertEqual([event["event"] for event in events], ["detected", "pneumatic_update", "acknowledged"])
            self.assertEqual([event["collision_id"] for event in events], ["collision-1"] * 3)
            self.assertTrue(all(event.get("wall_time") for event in events))
            self.assertNotEqual(events[0]["wall_time"], "forged")
            self.assertIsNotNone(datetime.fromisoformat(events[0]["wall_time"]).tzinfo)

    def test_start_failure_closes_open_streams_and_allows_a_retry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = SessionRecorder(Path(temp_dir))
            opened = []
            original_open = Path.open

            def open_or_fail(path, *args, **kwargs):
                if path.name == "vision.ndjson":
                    raise OSError("vision stream unavailable")
                handle = original_open(path, *args, **kwargs)
                opened.append(handle)
                return handle

            with self.assertRaisesRegex(OSError, "vision stream unavailable"):
                with patch.object(Path, "open", autospec=True, side_effect=open_or_fail):
                    recorder.start("COM21", 115200, "session-1")

            self.assertTrue(opened[0].closed)
            self.assertIsNone(recorder.session_dir)
            self.assertIsNone(recorder._telemetry)
            self.assertIsNone(recorder._collision)
            self.assertIsNone(recorder._pressure)

            retry_session = recorder.start("COM21", 115200, "session-2")
            self.assertTrue(retry_session.exists())
            recorder.close()

    def test_close_continues_cleanup_after_a_handle_close_failure(self):
        class CloseControlledHandle:
            def __init__(self, error: Exception | None = None) -> None:
                self.error = error
                self.close_called = False

            def close(self) -> None:
                self.close_called = True
                if self.error is not None:
                    raise self.error

        recorder = SessionRecorder(Path("unused"))
        failing = CloseControlledHandle(RuntimeError("telemetry close failed"))
        collision = CloseControlledHandle()
        pressure = CloseControlledHandle()
        recorder._telemetry = failing
        recorder._collision = collision
        recorder._pressure = pressure
        recorder._pressure_writer = object()
        recorder.session_dir = Path("unused-session")

        with self.assertRaisesRegex(RuntimeError, "telemetry close failed"):
            recorder.close()

        self.assertTrue(failing.close_called)
        self.assertTrue(collision.close_called)
        self.assertTrue(pressure.close_called)
        self.assertIsNone(recorder.session_dir)
        self.assertIsNone(recorder._telemetry)
        self.assertIsNone(recorder._collision)
        self.assertIsNone(recorder._pressure)
        self.assertIsNone(recorder._pressure_writer)
        recorder.close()


if __name__ == "__main__":
    unittest.main()
