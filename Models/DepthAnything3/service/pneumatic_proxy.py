from __future__ import annotations

import json
import re
import time
import urllib.request
from urllib.error import HTTPError
from typing import Callable

from frame_pipeline import LatestFrameStore


PNEUMATIC_DEVICE_FRESH_MS = 3_000
_COMMAND_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
_COMMANDS = {"inflate_pulse", "vent", "emergency_stop", "reset_fault", "save_calibration", "self_test"}


class PneumaticProxyError(RuntimeError):
    """The local PC service could not safely proxy a pneumatic request."""


class StaleDeviceError(PneumaticProxyError):
    pass


class PneumaticProtocolError(PneumaticProxyError):
    pass


def _http_post(url: str, token: str, payload: dict, timeout_s: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AIX-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as decode_error:
            raise OSError(f"pneumatic command returned HTTP {exc.code}") from decode_error
        if isinstance(payload, dict) and payload.get("type") == "pneumatic_ack":
            return payload
        raise OSError(f"pneumatic command returned HTTP {exc.code}")


def _http_get(url: str, token: str, timeout_s: float) -> dict:
    request = urllib.request.Request(url, headers={"X-AIX-Token": token}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        if response.status != 200:
            raise OSError(f"pneumatic config returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


class PneumaticProxy:
    def __init__(
        self,
        store: LatestFrameStore,
        *,
        token: str,
        post_transport: Callable[[str, str, dict, float], dict] = _http_post,
        get_transport: Callable[[str, str, float], dict] = _http_get,
        now_ms: Callable[[], int] | None = None,
        timeout_s: float = 0.8,
    ) -> None:
        self._store = store
        self._token = token
        self._post_transport = post_transport
        self._get_transport = get_transport
        self._now_ms = now_ms or (lambda: int(time.time() * 1000))
        self._timeout_s = timeout_s

    def _current_frame(self, device_id: str):
        frame = self._store.latest(device_id)
        if frame is None:
            raise StaleDeviceError("device has not uploaded a frame in this PC session")
        age_ms = self._now_ms() - frame.received_ts_ms
        if age_ms < 0 or age_ms > PNEUMATIC_DEVICE_FRESH_MS:
            raise StaleDeviceError(f"latest device frame is stale ({age_ms}ms)")
        return frame

    @staticmethod
    def _validate_command(command: dict) -> tuple[str, str]:
        command_id = command.get("command_id")
        command_name = command.get("command")
        if not isinstance(command_id, str) or not _COMMAND_ID.fullmatch(command_id):
            raise PneumaticProtocolError("command_id must be 1-64 URL-safe characters")
        if command_name not in _COMMANDS:
            raise PneumaticProtocolError("unsupported pneumatic command")
        if command_name == "save_calibration":
            for key in ("target_kpa", "max_kpa"):
                if not isinstance(command.get(key), (int, float)) or isinstance(command.get(key), bool):
                    raise PneumaticProtocolError(f"{key} is required for save_calibration")
        return command_id, command_name

    def command(self, device_id: str, command: dict) -> dict:
        command_id, command_name = self._validate_command(command)
        frame = self._current_frame(device_id)
        payload = {
            "type": "pneumatic_command",
            "version": 1,
            "device_id": frame.device_id,
            "boot_id": frame.boot_id,
            "command_id": command_id,
            "command": command_name,
        }
        if command_name == "save_calibration":
            payload.update(
                target_kpa=float(command["target_kpa"]),
                max_kpa=float(command["max_kpa"]),
            )
        url = f"http://{frame.source_ip}:8080/pneumatic/command"
        try:
            ack = self._post_transport(url, self._token, payload, self._timeout_s)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PneumaticProxyError(str(exc)) from exc
        if (
            not isinstance(ack, dict)
            or ack.get("type") != "pneumatic_ack"
            or ack.get("version") != 1
            or ack.get("boot_id") != frame.boot_id
            or ack.get("command_id") != command_id
            or not isinstance(ack.get("accepted"), bool)
        ):
            raise PneumaticProtocolError("invalid or mismatched pneumatic_ack")
        return ack

    def config(self, device_id: str) -> dict:
        frame = self._current_frame(device_id)
        url = f"http://{frame.source_ip}:8080/pneumatic/config"
        try:
            config = self._get_transport(url, self._token, self._timeout_s)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise PneumaticProxyError(str(exc)) from exc
        if (
            not isinstance(config, dict)
            or config.get("type") != "pneumatic_config"
            or config.get("version") != 2
            or config.get("device_id") != frame.device_id
            or config.get("boot_id") != frame.boot_id
        ):
            raise PneumaticProtocolError("invalid or mismatched pneumatic_config")
        return config
