from __future__ import annotations

import json
import re
from typing import Any

from .models import CameraStatusEvent, MotionEvent, PressureSample, VisionDepthEvent


class ParseError(ValueError):
    """Raised when a serial line is not supported telemetry."""


_LEGACY_PREFIX_RE = re.compile(r"\((?P<ts_ms>\d+)\).*PRESSURE,(?P<body>.*)$")
_LEGACY_BODY_RE = re.compile(r"PRESSURE,(?P<body>.*)$")
_PRESSURE_REQUIRED = ("seq", "ts_ms", "raw", "mv", "kpa", "filtered_kpa", "over_pressure", "valid")
_MOTION_REQUIRED = ("seq", "ts_ms", "speed_mps", "accel_mps2", "speed_valid", "accel_valid")
_CAMERA_STATUS_REQUIRED = (
    "seq", "ts_ms", "sensor", "width", "height", "pixel_format", "frame_bytes",
    "fps", "frames_ok", "capture_failures", "psram", "valid",
)
_VISION_DEPTH_REQUIRED = (
    "frame_seq", "capture_ts_ms", "model", "depth_kind", "depth_p10", "depth_median",
    "confidence_median", "latency_ms", "valid",
)


def parse_event_line(line: str) -> PressureSample | MotionEvent | CameraStatusEvent | VisionDepthEvent:
    text = line.strip()
    if not text:
        raise ParseError("empty line")
    if not text.startswith("{"):
        return _parse_legacy_pressure(text)
    payload = _load_json_object(text)
    event_type = payload.get("type")
    if event_type == "pressure":
        return _parse_pressure_payload(payload)
    if event_type == "motion":
        return _parse_motion_payload(payload)
    if event_type == "camera_status":
        return _parse_camera_status_payload(payload)
    if event_type == "vision_depth":
        return _parse_vision_depth_payload(payload)
    raise ParseError(f"unsupported json event type: {event_type}")


def parse_pressure_line(line: str) -> PressureSample:
    event = parse_event_line(line)
    if not isinstance(event, PressureSample):
        raise ParseError("line is not pressure telemetry")
    return event


def _load_json_object(text: str) -> dict[str, Any]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid json: {exc}") from exc
    if not isinstance(payload, dict):
        raise ParseError("json event is not an object")
    return payload


def _parse_pressure_payload(payload: dict[str, Any]) -> PressureSample:
    missing = [key for key in _PRESSURE_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"pressure json missing fields: {', '.join(missing)}")
    try:
        return PressureSample(
            seq=_as_int(payload["seq"], "seq"), ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
            raw=_as_int(payload["raw"], "raw"), mv=_as_int(payload["mv"], "mv"),
            kpa=_as_float(payload["kpa"], "kpa"), filtered_kpa=_as_float(payload["filtered_kpa"], "filtered_kpa"),
            over_pressure=_as_bool(payload["over_pressure"], "over_pressure"),
            valid=_as_bool(payload["valid"], "valid"), source="json",
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_motion_payload(payload: dict[str, Any]) -> MotionEvent:
    missing = [key for key in _MOTION_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"motion json missing fields: {', '.join(missing)}")
    try:
        return MotionEvent(
            seq=_as_int(payload["seq"], "seq"), ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
            speed_mps=_as_float(payload["speed_mps"], "speed_mps"), accel_mps2=_as_float(payload["accel_mps2"], "accel_mps2"),
            speed_valid=_as_bool(payload["speed_valid"], "speed_valid"),
            accel_valid=_as_bool(payload["accel_valid"], "accel_valid"), source="json",
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_camera_status_payload(payload: dict[str, Any]) -> CameraStatusEvent:
    missing = [key for key in _CAMERA_STATUS_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"camera_status missing fields: {', '.join(missing)}")
    try:
        return CameraStatusEvent(
            seq=_as_int(payload["seq"], "seq"), ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
            sensor=str(payload["sensor"]), width=_as_int(payload["width"], "width"),
            height=_as_int(payload["height"], "height"), pixel_format=str(payload["pixel_format"]),
            frame_bytes=_as_int(payload["frame_bytes"], "frame_bytes"), fps=_as_float(payload["fps"], "fps"),
            frames_ok=_as_int(payload["frames_ok"], "frames_ok"),
            capture_failures=_as_int(payload["capture_failures"], "capture_failures"),
            psram=_as_bool(payload["psram"], "psram"), valid=_as_bool(payload["valid"], "valid"),
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_vision_depth_payload(payload: dict[str, Any]) -> VisionDepthEvent:
    missing = [key for key in _VISION_DEPTH_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"vision_depth missing fields: {', '.join(missing)}")
    try:
        return VisionDepthEvent(
            frame_seq=_as_int(payload["frame_seq"], "frame_seq"),
            capture_ts_ms=_as_int(payload["capture_ts_ms"], "capture_ts_ms"),
            model=str(payload["model"]), depth_kind=str(payload["depth_kind"]),
            depth_p10=_as_float(payload["depth_p10"], "depth_p10"),
            depth_median=_as_float(payload["depth_median"], "depth_median"),
            confidence_median=_as_float(payload["confidence_median"], "confidence_median"),
            latency_ms=_as_float(payload["latency_ms"], "latency_ms"),
            valid=_as_bool(payload["valid"], "valid"),
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_legacy_pressure(text: str) -> PressureSample:
    ts_ms = 0
    match = _LEGACY_PREFIX_RE.search(text)
    if match:
        ts_ms = int(match.group("ts_ms"))
        body = match.group("body")
    else:
        match = _LEGACY_BODY_RE.search(text)
        if not match:
            raise ParseError("line is not pressure telemetry")
        body = match.group("body")
    fields = {key.strip(): value.strip() for part in body.split(",") if (key := part.partition("=")[0]) and "=" in part for value in [part.partition("=")[2]]}
    required = ("seq", "raw", "mv", "kpa", "filtered", "over", "valid")
    missing = [key for key in required if key not in fields]
    if missing:
        raise ParseError(f"legacy pressure line missing fields: {', '.join(missing)}")
    try:
        return PressureSample(seq=_as_int(fields["seq"], "seq"), ts_ms=ts_ms, raw=_as_int(fields["raw"], "raw"), mv=_as_int(fields["mv"], "mv"), kpa=_as_float(fields["kpa"], "kpa"), filtered_kpa=_as_float(fields["filtered"], "filtered"), over_pressure=_as_bool(fields["over"], "over"), valid=_as_bool(fields["valid"], "valid"), source="legacy")
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _as_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    return int(value)


def _as_float(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    return float(value)


def _as_bool(value: Any, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        if value.strip().lower() in ("1", "true"):
            return True
        if value.strip().lower() in ("0", "false"):
            return False
    raise ValueError(f"{name} must be a boolean")
