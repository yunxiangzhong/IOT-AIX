from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6 import QtGui


class SessionRecorder:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.session_dir: Path | None = None
        self._metadata: dict[str, Any] | None = None
        self._telemetry = None
        self._vision = None
        self._action = None
        self._pneumatic = None
        self._road_hazard = None
        self._collision = None
        self._model_log = None
        self._pressure = None
        self._pressure_writer = None
        self._saved_frames: set[tuple[int, int]] = set()
        self._saved_actions: set[tuple[int, str, str, bool]] = set()

    def start(self, serial_port: str, baudrate: int, session_id: str) -> Path:
        self.close()
        self.root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_dir = self.root / stamp
        suffix = 2
        while session_dir.exists():
            session_dir = self.root / f"{stamp}_{suffix:02d}"
            suffix += 1
        (session_dir / "frames").mkdir(parents=True)
        self.session_dir = session_dir
        self._metadata = {
            "session_id": session_id,
            "serial_port": serial_port,
            "baudrate": baudrate,
            "started_at": datetime.now().astimezone().isoformat(),
            "ended_at": None,
            "status": "recording",
            "pneumatic_config": None,
        }
        self._write_metadata()
        self._telemetry = (session_dir / "telemetry.ndjson").open("w", encoding="utf-8")
        self._vision = (session_dir / "vision.ndjson").open("w", encoding="utf-8")
        self._action = (session_dir / "action.ndjson").open("w", encoding="utf-8")
        self._pneumatic = (session_dir / "pneumatic.ndjson").open("w", encoding="utf-8")
        self._road_hazard = (session_dir / "road_hazard.ndjson").open("w", encoding="utf-8")
        self._collision = (session_dir / "collision_events.jsonl").open("w", encoding="utf-8")
        self._model_log = (session_dir / "model.log").open("w", encoding="utf-8")
        self._pressure = (session_dir / "pressure.csv").open("w", newline="", encoding="utf-8")
        self._pressure_writer = csv.writer(self._pressure)
        self._pressure_writer.writerow(["seq", "ts_ms", "raw", "mv", "kpa", "filtered_kpa", "over_pressure", "valid", "source"])
        return session_dir

    def save_frame(self, data: bytes, frame_seq: int, capture_ts_ms: int) -> Path:
        if self.session_dir is None:
            raise RuntimeError("recording session is not active")
        path = self.session_dir / "frames" / f"frame_{frame_seq:08d}_{capture_ts_ms}.jpg"
        identity = (frame_seq, capture_ts_ms)
        if identity in self._saved_frames:
            return path
        path.write_bytes(data)
        self._saved_frames.add(identity)
        return path

    def save_png_snapshot(self, data: bytes) -> Path:
        """Atomically materialize the latest analysed image as a PC-side PNG."""
        image = QtGui.QImage.fromData(data)
        if image.isNull():
            raise ValueError("processed frame is not a valid image")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / "latest_processed.png"
        temporary = self.root / ".latest_processed.tmp"
        if not image.save(str(temporary), "PNG"):
            raise OSError("unable to encode processed PNG snapshot")
        temporary.replace(path)
        return path

    def record_event(self, raw_line: str) -> None:
        if self._telemetry is None:
            return
        self._write_line(self._telemetry, {"wall_time": datetime.now().astimezone().isoformat(), "kind": "serial", "raw": raw_line})

    def record_vision(self, payload: dict[str, Any]) -> None:
        if self._vision is None:
            return
        self._write_line(self._vision, {"wall_time": datetime.now().astimezone().isoformat(), **payload})

    def record_action(self, payload: dict[str, Any]) -> None:
        if self._action is None:
            return
        identity = (
            int(payload.get("frame_seq", -1)),
            str(payload.get("action_state", "")),
            str(payload.get("rgb_pattern", "")),
            bool(payload.get("stale", False)),
        )
        if identity in self._saved_actions:
            return
        self._saved_actions.add(identity)
        self._write_line(self._action, {"wall_time": datetime.now().astimezone().isoformat(), **payload})

    def record_pneumatic(self, payload: dict[str, Any]) -> None:
        if self._pneumatic is None:
            return
        self._write_line(self._pneumatic, {"wall_time": datetime.now().astimezone().isoformat(), **payload})

    def record_pneumatic_config(self, payload: dict[str, Any]) -> None:
        if self._metadata is not None:
            self._metadata["pneumatic_config"] = payload
            self._write_metadata()
        self.record_pneumatic(payload)

    def record_road_hazard(self, payload: dict[str, Any]) -> None:
        if self._road_hazard is None:
            return
        self._write_line(self._road_hazard, {"wall_time": datetime.now().astimezone().isoformat(), **payload})

    def record_collision(self, payload: dict[str, Any]) -> None:
        if self._collision is None:
            return
        self._write_line(self._collision, {"wall_time": datetime.now().astimezone().isoformat(), **payload})

    def append_model_log(self, line: str) -> None:
        if self._model_log is None:
            return
        self._model_log.write(line.rstrip("\r\n") + "\n")
        self._model_log.flush()

    def record_pressure(self, sample) -> None:
        if self._pressure_writer is None:
            return
        self._pressure_writer.writerow([
            sample.seq, sample.ts_ms, sample.raw, sample.mv, f"{sample.kpa:.3f}",
            f"{sample.filtered_kpa:.3f}", int(sample.over_pressure), int(sample.valid), sample.source,
        ])
        self._pressure.flush()

    def close(self) -> None:
        for handle in (self._telemetry, self._vision, self._action, self._pneumatic, self._road_hazard, self._collision, self._model_log, self._pressure):
            if handle is not None:
                handle.close()
        self._telemetry = self._vision = self._action = self._pneumatic = self._road_hazard = self._collision = self._model_log = self._pressure = None
        self._pressure_writer = None
        self._saved_frames.clear()
        self._saved_actions.clear()
        if self._metadata is not None:
            self._metadata["ended_at"] = datetime.now().astimezone().isoformat()
            self._metadata["status"] = "closed"
            self._write_metadata()
        self.session_dir = None
        self._metadata = None

    def _write_metadata(self) -> None:
        if self.session_dir is not None and self._metadata is not None:
            (self.session_dir / "session.json").write_text(
                json.dumps(self._metadata, ensure_ascii=False, indent=2), encoding="utf-8"
            )

    @staticmethod
    def _write_line(handle, payload: dict[str, Any]) -> None:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()
