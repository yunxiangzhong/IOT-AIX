from __future__ import annotations

import json
import re
from typing import Any

from .models import ActionStatusEvent, CameraPreviewEvent, CameraStatusEvent, DetectionBox, MotionEvent, PneumaticStatusEvent, PressureSample, RiskAckEvent, RoadHazardStatusEvent, VisionDepthEvent, VoiceStatusEvent


class ParseError(ValueError):
    """Raised when a serial line is not supported telemetry."""


_LEGACY_PREFIX_RE = re.compile(r"\((?P<ts_ms>\d+)\).*PRESSURE,(?P<body>.*)$")
_LEGACY_BODY_RE = re.compile(r"PRESSURE,(?P<body>.*)$")
_PRESSURE_REQUIRED = ("seq", "ts_ms", "raw", "mv", "kpa", "filtered_kpa", "over_pressure", "valid")
_MOTION_REQUIRED = ("seq", "ts_ms", "speed_mps", "accel_mps2", "speed_valid", "accel_valid")
_MOTION_V2_REQUIRED = ("seq", "ts_ms", "accel_g", "gyro_dps", "accel_norm_g", "tilt_deg", "impact", "rapid_tilt", "danger_latched", "calibrated")
_PNEUMATIC_STATUS_REQUIRED = (
    "ts_ms", "state", "fault", "trigger", "operation", "pump_on", "valve_on", "pressure_kpa",
    "pressure_valid", "pressure_age_ms", "vision_state", "vision_fresh", "mpu_available", "mpu_calibrated",
    "impact", "rapid_tilt",
)
_CAMERA_STATUS_REQUIRED = (
    "seq", "ts_ms", "sensor", "width", "height", "pixel_format", "frame_bytes",
    "fps", "frames_ok", "capture_failures", "psram", "valid",
)
_CAMERA_PREVIEW_REQUIRED = ("valid", "url", "ip", "port", "reason")
_VISION_DEPTH_REQUIRED = (
    "frame_seq", "capture_ts_ms", "model", "depth_kind", "depth_p10", "depth_median",
    "confidence_median", "latency_ms", "valid",
)
_RISK_ACK_REQUIRED = ("frame_seq", "risk_score", "risk_band", "valid", "stale")
_ACTION_STATUS_REQUIRED = (
    "ts_ms", "frame_seq", "risk_score", "valid", "stale", "action_state", "rgb_pattern",
)
_VOICE_STATUS_REQUIRED = ("state", "command_id", "track", "error")
_ROAD_HAZARD_STATUS_REQUIRED = ("state", "event_id", "effective_rgb_pattern", "reason")


def parse_event_line(line: str) -> PressureSample | MotionEvent | PneumaticStatusEvent | CameraStatusEvent | CameraPreviewEvent | VisionDepthEvent | RiskAckEvent | ActionStatusEvent | VoiceStatusEvent | RoadHazardStatusEvent:
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
    if event_type == "pneumatic_status":
        return _parse_pneumatic_status_payload(payload)
    if event_type == "camera_status":
        return _parse_camera_status_payload(payload)
    if event_type == "camera_preview":
        return _parse_camera_preview_payload(payload)
    if event_type == "vision_depth":
        return _parse_vision_depth_payload(payload)
    if event_type == "risk_ack":
        return _parse_risk_ack_payload(payload)
    if event_type == "action_status":
        return _parse_action_status_payload(payload)
    if event_type == "voice_status":
        return _parse_voice_status_payload(payload)
    if event_type == "road_hazard_status":
        return _parse_road_hazard_status_payload(payload)
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
    if payload.get("version") == 2:
        missing = [key for key in _MOTION_V2_REQUIRED if key not in payload]
        if missing:
            raise ParseError(f"motion v2 json missing fields: {', '.join(missing)}")
        accel = payload["accel_g"]
        gyro = payload["gyro_dps"]
        if not isinstance(accel, dict) or not isinstance(gyro, dict):
            raise ParseError("motion v2 axes must be objects")
        try:
            return MotionEvent(
                seq=_as_int(payload["seq"], "seq"), ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
                speed_mps=_as_float(payload.get("speed_mps", 0.0), "speed_mps"),
                accel_mps2=_as_float(payload["accel_norm_g"], "accel_norm_g") * 9.80665,
                speed_valid=_as_bool(payload.get("speed_valid", False), "speed_valid"), accel_valid=True,
                accel_x_g=_as_float(accel.get("x"), "accel_g.x"), accel_y_g=_as_float(accel.get("y"), "accel_g.y"),
                accel_z_g=_as_float(accel.get("z"), "accel_g.z"), gyro_x_dps=_as_float(gyro.get("x"), "gyro_dps.x"),
                gyro_y_dps=_as_float(gyro.get("y"), "gyro_dps.y"), gyro_z_dps=_as_float(gyro.get("z"), "gyro_dps.z"),
                accel_norm_g=_as_float(payload["accel_norm_g"], "accel_norm_g"),
                tilt_deg=_as_float(payload["tilt_deg"], "tilt_deg"), impact=_as_bool(payload["impact"], "impact"),
                rapid_tilt=_as_bool(payload["rapid_tilt"], "rapid_tilt"),
                danger_latched=_as_bool(payload["danger_latched"], "danger_latched"),
                calibrated=_as_bool(payload["calibrated"], "calibrated"), source="json-v2",
            )
        except (TypeError, ValueError) as exc:
            raise ParseError(str(exc)) from exc
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


def _parse_pneumatic_status_payload(payload: dict[str, Any]) -> PneumaticStatusEvent:
    missing = [key for key in _PNEUMATIC_STATUS_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"pneumatic_status missing fields: {', '.join(missing)}")
    try:
        state = str(payload["state"])
        if state not in {"disabled", "vented", "prime_valve", "inflating", "holding", "venting", "cooldown", "fault_vent"}:
            raise ValueError("pneumatic state is invalid")
        return PneumaticStatusEvent(
            ts_ms=_as_int(payload["ts_ms"], "ts_ms"), state=state, fault=str(payload["fault"]),
            trigger=str(payload["trigger"]), operation=_as_int(payload["operation"], "operation"),
            pump_on=_as_bool(payload["pump_on"], "pump_on"), valve_on=_as_bool(payload["valve_on"], "valve_on"),
            pressure_kpa=_as_float(payload["pressure_kpa"], "pressure_kpa"),
            pressure_valid=_as_bool(payload["pressure_valid"], "pressure_valid"),
            pressure_age_ms=_as_int(payload["pressure_age_ms"], "pressure_age_ms"),
            vision_state=str(payload["vision_state"]), vision_fresh=_as_bool(payload["vision_fresh"], "vision_fresh"),
            mpu_available=_as_bool(payload["mpu_available"], "mpu_available"),
            mpu_calibrated=_as_bool(payload["mpu_calibrated"], "mpu_calibrated"),
            impact=_as_bool(payload["impact"], "impact"), rapid_tilt=_as_bool(payload["rapid_tilt"], "rapid_tilt"),
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


def _parse_camera_preview_payload(payload: dict[str, Any]) -> CameraPreviewEvent:
    missing = [key for key in _CAMERA_PREVIEW_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"camera_preview missing fields: {', '.join(missing)}")
    try:
        valid = _as_bool(payload["valid"], "valid")
        url = str(payload["url"])
        ip = str(payload["ip"])
        port = _as_int(payload["port"], "port")
        reason = str(payload["reason"])
        if valid and (not url.startswith("http://") or not url.endswith("/capture.jpg")):
            raise ValueError("camera_preview url must be an http capture.jpg endpoint")
        if port < 1 or port > 65535:
            raise ValueError("camera_preview port is outside 1-65535")
        return CameraPreviewEvent(valid=valid, url=url, ip=ip, port=port, reason=reason)
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


def _parse_risk_ack_payload(payload: dict[str, Any]) -> RiskAckEvent:
    missing = [key for key in _RISK_ACK_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"risk_ack missing fields: {', '.join(missing)}")
    try:
        score = _as_int(payload["risk_score"], "risk_score")
        if score < 0 or score > 100:
            raise ValueError("risk_score must be between 0 and 100")
        band = str(payload["risk_band"])
        if band not in {"low", "attention", "high", "critical"}:
            raise ValueError("risk_band is invalid")
        return RiskAckEvent(
            frame_seq=_as_int(payload["frame_seq"], "frame_seq"),
            risk_score=score,
            risk_band=band,
            valid=_as_bool(payload["valid"], "valid"),
            stale=_as_bool(payload["stale"], "stale"),
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_action_status_payload(payload: dict[str, Any]) -> ActionStatusEvent:
    missing = [key for key in _ACTION_STATUS_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"action_status missing fields: {', '.join(missing)}")
    try:
        score = _as_int(payload["risk_score"], "risk_score")
        state = str(payload["action_state"])
        pattern = str(payload["rgb_pattern"])
        if score < 0 or score > 100:
            raise ValueError("risk_score must be between 0 and 100")
        if state not in {"loading", "safe", "attention", "high", "critical", "fault"}:
            raise ValueError("action_state is invalid")
        if pattern not in {
            "blue_blink_1hz", "green_solid", "yellow_blink_1hz",
            "orange_blink_2hz", "red_double_pulse", "purple_blink_1hz",
        }:
            raise ValueError("rgb_pattern is invalid")
        return ActionStatusEvent(
            ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
            frame_seq=_as_int(payload["frame_seq"], "frame_seq"),
            risk_score=score,
            valid=_as_bool(payload["valid"], "valid"),
            stale=_as_bool(payload["stale"], "stale"),
            action_state=state,
            rgb_pattern=pattern,
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_voice_status_payload(payload: dict[str, Any]) -> VoiceStatusEvent:
    missing = [key for key in _VOICE_STATUS_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"voice_status missing fields: {', '.join(missing)}")
    try:
        state = str(payload["state"])
        if state not in {"initializing", "ready", "playing", "finished", "error"}:
            raise ValueError("voice_status state is invalid")
        track = _as_int(payload["track"], "track")
        if track < 0 or track > 255:
            raise ValueError("voice_status track is invalid")
        return VoiceStatusEvent(state, str(payload["command_id"]), track, str(payload["error"]))
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_road_hazard_status_payload(payload: dict[str, Any]) -> RoadHazardStatusEvent:
    missing = [key for key in _ROAD_HAZARD_STATUS_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"road_hazard_status missing fields: {', '.join(missing)}")
    state = str(payload["state"])
    if state not in {"active", "expired", "rejected"}:
        raise ParseError("road_hazard_status state is invalid")
    return RoadHazardStatusEvent(
        state, str(payload["event_id"]), str(payload.get("severity", "unknown")),
        str(payload["effective_rgb_pattern"]), str(payload["reason"]),
    )


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
