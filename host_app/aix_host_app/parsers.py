from __future__ import annotations

import json
import re
from typing import Any

from .models import PressureSample


class ParseError(ValueError):
    """Raised when a serial line is not a pressure telemetry event."""


_LEGACY_PREFIX_RE = re.compile(r"\((?P<ts_ms>\d+)\).*PRESSURE,(?P<body>.*)$")
_LEGACY_BODY_RE = re.compile(r"PRESSURE,(?P<body>.*)$")
_JSON_REQUIRED = (
    "seq",
    "ts_ms",
    "raw",
    "mv",
    "kpa",
    "filtered_kpa",
    "over_pressure",
    "valid",
)


def parse_pressure_line(line: str) -> PressureSample:
    text = line.strip()
    if not text:
        raise ParseError("empty line")

    if text.startswith("{"):
        return _parse_pressure_json(text)
    return _parse_legacy_pressure(text)


def _parse_pressure_json(text: str) -> PressureSample:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ParseError(f"invalid json: {exc}") from exc

    if not isinstance(payload, dict):
        raise ParseError("json event is not an object")
    if payload.get("type") != "pressure":
        raise ParseError("json event is not a pressure sample")

    missing = [key for key in _JSON_REQUIRED if key not in payload]
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
