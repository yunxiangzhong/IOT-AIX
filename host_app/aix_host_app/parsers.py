from __future__ import annotations

import json
import re
from typing import Any

from .models import ActuatorEvent, MotionEvent, PressureSample, RiskEvent


class ParseError(ValueError):
    """Raised when a serial line is not a supported telemetry event."""


_LEGACY_PREFIX_RE = re.compile(r"\((?P<ts_ms>\d+)\).*PRESSURE,(?P<body>.*)$")
_LEGACY_BODY_RE = re.compile(r"PRESSURE,(?P<body>.*)$")
_PRESSURE_REQUIRED = (
    "seq",
    "ts_ms",
    "raw",
    "mv",
    "kpa",
    "filtered_kpa",
    "over_pressure",
    "valid",
)
_RISK_REQUIRED = (
    "seq",
    "ts_ms",
    "level",
    "target_pct",
    "reason",
    "vision_stale",
    "pressure_safe",
)
_ACTUATOR_REQUIRED = ("seq", "ts_ms", "mode", "target_pct", "pump", "valve")
_MOTION_REQUIRED = (
    "seq",
    "ts_ms",
    "speed_mps",
    "accel_mps2",
    "speed_valid",
    "accel_valid",
)


def parse_event_line(line: str) -> PressureSample | RiskEvent | ActuatorEvent | MotionEvent:
    text = line.strip()
    if not text:
        raise ParseError("empty line")

    if not text.startswith("{"):
        return _parse_legacy_pressure(text)

    payload = _load_json_object(text)
    event_type = payload.get("type")
    if event_type == "pressure":
        return _parse_pressure_payload(payload)
    if event_type == "risk":
        return _parse_risk_payload(payload)
    if event_type == "actuator":
        return _parse_actuator_payload(payload)
    if event_type == "motion":
        return _parse_motion_payload(payload)
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
            seq=_as_int(payload["seq"], "seq"),
            ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
            raw=_as_int(payload["raw"], "raw"),
            mv=_as_int(payload["mv"], "mv"),
            kpa=_as_float(payload["kpa"], "kpa"),
            filtered_kpa=_as_float(payload["filtered_kpa"], "filtered_kpa"),
            over_pressure=_as_bool(payload["over_pressure"], "over_pressure"),
            valid=_as_bool(payload["valid"], "valid"),
            source="json",
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_risk_payload(payload: dict[str, Any]) -> RiskEvent:
    missing = [key for key in _RISK_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"risk json missing fields: {', '.join(missing)}")

    try:
        return RiskEvent(
            seq=_as_int(payload["seq"], "seq"),
            ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
            level=_as_int(payload["level"], "level"),
            target_pct=_as_int(payload["target_pct"], "target_pct"),
            reason=str(payload["reason"]),
            vision_stale=_as_bool(payload["vision_stale"], "vision_stale"),
            pressure_safe=_as_bool(payload["pressure_safe"], "pressure_safe"),
            pressure_state=str(payload.get("pressure_state", "enabled")),
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_actuator_payload(payload: dict[str, Any]) -> ActuatorEvent:
    missing = [key for key in _ACTUATOR_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"actuator json missing fields: {', '.join(missing)}")

    try:
        return ActuatorEvent(
            seq=_as_int(payload["seq"], "seq"),
            ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
            mode=str(payload["mode"]),
            target_pct=_as_int(payload["target_pct"], "target_pct"),
            pump=str(payload["pump"]),
            valve=str(payload["valve"]),
        )
    except (TypeError, ValueError) as exc:
        raise ParseError(str(exc)) from exc


def _parse_motion_payload(payload: dict[str, Any]) -> MotionEvent:
    missing = [key for key in _MOTION_REQUIRED if key not in payload]
    if missing:
        raise ParseError(f"motion json missing fields: {', '.join(missing)}")

    try:
        return MotionEvent(
            seq=_as_int(payload["seq"], "seq"),
            ts_ms=_as_int(payload["ts_ms"], "ts_ms"),
            speed_mps=_as_float(payload["speed_mps"], "speed_mps"),
            accel_mps2=_as_float(payload["accel_mps2"], "accel_mps2"),
            speed_valid=_as_bool(payload["speed_valid"], "speed_valid"),
            accel_valid=_as_bool(payload["accel_valid"], "accel_valid"),
            source="json",
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

    fields: dict[str, str] = {}
    for part in body.split(","):
        key, sep, value = part.partition("=")
        if not sep:
            continue
        fields[key.strip()] = value.strip()

    required = ("seq", "raw", "mv", "kpa", "filtered", "over", "valid")
    missing = [key for key in required if key not in fields]
    if missing:
        raise ParseError(f"legacy pressure line missing fields: {', '.join(missing)}")

    try:
        return PressureSample(
            seq=_as_int(fields["seq"], "seq"),
            ts_ms=ts_ms,
            raw=_as_int(fields["raw"], "raw"),
            mv=_as_int(fields["mv"], "mv"),
            kpa=_as_float(fields["kpa"], "kpa"),
            filtered_kpa=_as_float(fields["filtered"], "filtered"),
            over_pressure=_as_bool(fields["over"], "over"),
            valid=_as_bool(fields["valid"], "valid"),
            source="legacy",
        )
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
        normalized = value.strip().lower()
        if normalized in ("1", "true"):
            return True
        if normalized in ("0", "false"):
            return False
    raise ValueError(f"{name} must be a boolean")
