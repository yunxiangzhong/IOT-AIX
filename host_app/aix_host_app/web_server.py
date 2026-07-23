"""Local browser dashboard for the AIX host stack.

The server deliberately binds to loopback only.  It owns the serial reader,
proxies the existing local DA3 service and exposes no actuator endpoint except
the already authenticated PC-side pneumatic proxy on port 8008.
"""
from __future__ import annotations

import argparse
import json
import os
import threading
import time
import uuid
from dataclasses import asdict, is_dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from .parsers import ParseError, parse_event_line


WEB_ROOT = Path(__file__).with_name("web")
POLL_INTERVAL_S = 0.5
SERIAL_BAUDRATE = 115200
MAX_LOG_LINES = 160
COMMANDS = {"inflate_pulse", "vent", "emergency_stop", "reset_fault", "save_calibration"}


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    return value


def _request_json(url: str, *, method: str = "GET", payload: dict | None = None, timeout: float = 1.5) -> dict:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8") if payload is not None else None
    request = Request(url, data=body, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    with urlopen(request, timeout=timeout) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("local service returned a non-object response")
    return result


class WebRuntime:
    def __init__(self, *, service_url: str, device_id: str) -> None:
        self.service_url = service_url.rstrip("/")
        self.device_id = device_id
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._serial_stop = threading.Event()
        self._serial_thread: threading.Thread | None = None
        self._serial_port = ""
        self._serial_open = False
        self._telemetry_confirmed = False
        self._serial_error = ""
        self._events: dict[str, Any] = {}
        self._chain_state: dict[str, Any] = {}
        self._health: dict[str, Any] = {}
        self._chain_error = ""
        self._logs: list[str] = []
        self._poll_thread = threading.Thread(target=self._poll_loop, name="aix-web-poll", daemon=True)

    def start(self) -> None:
        self._poll_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self.disconnect()
        self._poll_thread.join(timeout=2)

    def ports(self) -> list[dict[str, Any]]:
        from serial.tools import list_ports

        result = []
        for port in list_ports.comports():
            result.append({
                "device": port.device,
                "description": port.description or "n/a",
                "vid": port.vid,
                "pid": port.pid,
                "serial_number": port.serial_number or "",
            })
        return result

    def connect(self, port: str) -> None:
        if not isinstance(port, str) or not port.strip():
            raise ValueError("请选择串口")
        available = {item["device"] for item in self.ports()}
        if port not in available:
            raise ValueError(f"串口 {port} 当前未枚举")
        self.disconnect()
        with self._lock:
            self._serial_port = port
            self._serial_open = False
            self._telemetry_confirmed = False
            self._serial_error = ""
            self._serial_stop.clear()
            self._append_log(f"正在打开 {port}，等待真实 AIX 遥测确认")
            self._serial_thread = threading.Thread(target=self._serial_loop, args=(port,), name="aix-web-serial", daemon=True)
            self._serial_thread.start()

    def disconnect(self) -> None:
        self._serial_stop.set()
        thread = self._serial_thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)
        with self._lock:
            self._serial_thread = None
            self._serial_open = False
            self._telemetry_confirmed = False
            self._serial_port = ""

    def state(self) -> dict[str, Any]:
        with self._lock:
            return {
                "device_id": self.device_id,
                "service_url": self.service_url,
                "serial": {
                    "port": self._serial_port,
                    "open": self._serial_open,
                    "confirmed": self._telemetry_confirmed,
                    "error": self._serial_error,
                },
                "chain": self._chain_state,
                "health": self._health,
                "chain_error": self._chain_error,
                "events": {key: _jsonable(value) for key, value in self._events.items()},
                "logs": list(self._logs),
                "server_ts_ms": int(time.time() * 1000),
            }

    def pneumatic(self, command: dict[str, Any]) -> dict:
        name = command.get("command")
        if name not in COMMANDS:
            raise ValueError("不支持的气动命令")
        payload: dict[str, Any] = {"command_id": f"web-{uuid.uuid4().hex}", "command": name}
        if name == "save_calibration":
            for key in ("target_kpa", "max_kpa"):
                value = command.get(key)
                if type(value) not in (int, float):
                    raise ValueError(f"{key} 必须是数字")
                payload[key] = float(value)
            payload["max_inflate_ms"] = 5000
        return _request_json(
            f"{self.service_url}/v1/pneumatic/command?device_id={self.device_id}", method="POST", payload=payload, timeout=2.0
        )

    def pneumatic_config(self) -> dict:
        return _request_json(f"{self.service_url}/v1/pneumatic/config?device_id={self.device_id}", timeout=1.5)

    def snapshot(self) -> tuple[bytes, dict[str, str]]:
        request = Request(f"{self.service_url}/v1/frame/processed.jpg?device_id={self.device_id}")
        with urlopen(request, timeout=1.5) as response:
            return response.read(), {key: value for key, value in response.headers.items() if key.lower().startswith("x-")}

    def _poll_loop(self) -> None:
        while not self._stop.wait(POLL_INTERVAL_S):
            try:
                chain = _request_json(f"{self.service_url}/v1/state/latest?device_id={self.device_id}")
                with self._lock:
                    self._chain_state = chain
                    self._chain_error = ""
            except (URLError, HTTPError, ValueError, OSError) as exc:
                with self._lock:
                    self._chain_error = str(exc)
            try:
                health = _request_json(f"{self.service_url}/healthz", timeout=1.0)
                with self._lock:
                    self._health = health
            except (URLError, HTTPError, ValueError, OSError):
                pass

    def _serial_loop(self, port: str) -> None:
        try:
            import serial

            with serial.Serial(port, SERIAL_BAUDRATE, timeout=0.2) as connection:
                with self._lock:
                    self._serial_open = True
                    self._append_log(f"串口 {port} 已打开，等待 AIX 协议数据")
                while not self._serial_stop.is_set() and not self._stop.is_set():
                    raw = connection.readline()
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue
                    self._accept_serial_line(line)
        except Exception as exc:
            with self._lock:
                self._serial_error = f"串口读取失败：{exc}"
                self._append_log(self._serial_error)
        finally:
            with self._lock:
                self._serial_open = False

    def _accept_serial_line(self, line: str) -> None:
        try:
            event = parse_event_line(line)
        except ParseError:
            return
        key = type(event).__name__.removesuffix("Event").removesuffix("Sample").lower()
        with self._lock:
            self._events[key] = event
            self._telemetry_confirmed = True
            self._serial_error = ""
            self._append_log(line)

    def _append_log(self, text: str) -> None:
        self._logs.append(text)
        del self._logs[:-MAX_LOG_LINES]


class DashboardHandler(BaseHTTPRequestHandler):
    runtime: WebRuntime

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/state":
            return self._send_json(HTTPStatus.OK, self.runtime.state())
        if parsed.path == "/api/ports":
            return self._send_json(HTTPStatus.OK, {"ports": self.runtime.ports()})
        if parsed.path == "/api/pneumatic/config":
            return self._proxy_json(self.runtime.pneumatic_config)
        if parsed.path == "/api/snapshot":
            return self._snapshot()
        return self._static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if not isinstance(payload, dict):
                raise ValueError("请求体必须是 JSON 对象")
            if parsed.path == "/api/connect":
                self.runtime.connect(str(payload.get("port", "")))
                return self._send_json(HTTPStatus.OK, self.runtime.state()["serial"])
            if parsed.path == "/api/disconnect":
                self.runtime.disconnect()
                return self._send_json(HTTPStatus.OK, self.runtime.state()["serial"])
            if parsed.path == "/api/pneumatic/command":
                return self._proxy_json(lambda: self.runtime.pneumatic(payload))
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def _proxy_json(self, callback) -> None:
        try:
            self._send_json(HTTPStatus.OK, callback())
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            self._send_json(exc.code, {"error": body or f"upstream HTTP {exc.code}"})
        except (URLError, OSError, ValueError) as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})

    def _snapshot(self) -> None:
        try:
            data, headers = self.runtime.snapshot()
        except (HTTPError, URLError, OSError) as exc:
            self._send_json(HTTPStatus.BAD_GATEWAY, {"error": str(exc)})
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-store")
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path: str) -> None:
        relative = "index.html" if path in {"/", ""} else path.lstrip("/")
        candidate = (WEB_ROOT / relative).resolve()
        if WEB_ROOT not in candidate.parents or not candidate.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        content_type = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "application/javascript; charset=utf-8"}.get(candidate.suffix, "application/octet-stream")
        data = candidate.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int | HTTPStatus, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=False, default=_jsonable).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(port: int = 9696) -> None:
    runtime = WebRuntime(
        service_url=os.environ.get("AIX_SERVICE_URL", "http://127.0.0.1:8008"),
        device_id=os.environ.get("AIX_DEVICE_ID", "aix-helmet-01"),
    )
    DashboardHandler.runtime = runtime
    server = ThreadingHTTPServer(("127.0.0.1", port), DashboardHandler)
    runtime.start()
    print(f"AIX web dashboard ready: http://127.0.0.1:{port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        server.server_close()
        runtime.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="AIX local web dashboard")
    parser.add_argument("--port", type=int, default=9696)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be between 1024 and 65535")
    serve(args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
