from __future__ import annotations

import json
import http.client
import re
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

from frame_pipeline import ChainStateRepository, LatestFrameStore


class RoadHazardValidationError(ValueError):
    pass


class RoadHazardConflictError(ValueError):
    pass


class RoadHazardDeliveryError(RuntimeError):
    pass


class RoadHazardUnavailableError(RuntimeError):
    pass


_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}$")
_SEVERITIES = {"attention", "high", "critical"}
_DIRECTIONS = {"left", "right", "front", "rear"}
_FIELDS = (
    "event_id", "device_id", "camera_id", "intersection_id", "direction",
    "object_type", "eta_ms", "severity", "ttl_ms", "simulated", "message_code",
)


def _positive_int(payload: dict, field: str) -> int:
    value = payload.get(field)
    if type(value) is not int or value <= 0:
        raise RoadHazardValidationError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class RoadHazardEvent:
    event_id: str
    device_id: str
    camera_id: str
    intersection_id: str
    direction: str
    object_type: str
    eta_ms: int
    severity: str
    ttl_ms: int
    simulated: bool
    message_code: str

    @classmethod
    def from_payload(cls, payload: object) -> "RoadHazardEvent":
        if not isinstance(payload, dict):
            raise RoadHazardValidationError("road hazard must be a JSON object")
        if set(payload) != set(_FIELDS):
            raise RoadHazardValidationError("road hazard fields are missing or unknown")
        values = {}
        for field in ("event_id", "device_id", "camera_id", "intersection_id", "object_type", "message_code"):
            value = payload[field]
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise RoadHazardValidationError(f"{field} must be 1-64 URL-safe characters")
            values[field] = value
        direction = payload["direction"]
        severity = payload["severity"]
        if not isinstance(direction, str) or direction not in _DIRECTIONS:
            raise RoadHazardValidationError("direction is invalid")
        if not isinstance(severity, str) or severity not in _SEVERITIES:
            raise RoadHazardValidationError("severity is invalid")
        if type(payload["simulated"]) is not bool:
            raise RoadHazardValidationError("simulated must be boolean")
        return cls(
            **values, direction=direction, severity=severity, simulated=payload["simulated"],
            eta_ms=_positive_int(payload, "eta_ms"), ttl_ms=_positive_int(payload, "ttl_ms"),
        )

    def content(self) -> dict:
        return {field: getattr(self, field) for field in _FIELDS}

    def snapshot(self) -> dict:
        return dict(self.content())

    def delivery_payload(self, boot_id: str, remaining_ttl_ms: int) -> dict:
        return {"type": "road_hazard", "version": 1, **self.content(), "ttl_ms": remaining_ttl_ms, "boot_id": boot_id}


class RoadHazardRepository:
    def __init__(self, *, retention_ms: int = 60_000, max_events: int = 256, clock: Callable[[], int] | None = None) -> None:
        if retention_ms <= 0 or max_events <= 0:
            raise ValueError("repository retention and maximum must be positive")
        self._lock = threading.Lock()
        self._retention_ms = retention_ms
        self._max_events = max_events
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._events: dict[str, tuple[RoadHazardEvent, int | None]] = {}

    def _cleanup_locked(self, now_ms: int) -> None:
        for event_id, (_event, terminal_ms) in list(self._events.items()):
            if terminal_ms is not None and now_ms - terminal_ms >= self._retention_ms:
                del self._events[event_id]
        if len(self._events) <= self._max_events:
            return
        terminal = sorted(
            ((terminal_ms, event_id) for event_id, (_event, terminal_ms) in self._events.items() if terminal_ms is not None),
            key=lambda item: item[0],
        )
        for _terminal_ms, event_id in terminal:
            if len(self._events) <= self._max_events:
                break
            del self._events[event_id]

    def accept(self, event: RoadHazardEvent) -> bool:
        with self._lock:
            self._cleanup_locked(self._clock())
            record = self._events.get(event.event_id)
            previous = record[0] if record is not None else None
            if previous is None:
                self._events[event.event_id] = (event, None)
                self._cleanup_locked(self._clock())
                return True
            if previous == event:
                return False
            raise RoadHazardConflictError("event_id already exists with different content")

    def discard(self, event: RoadHazardEvent) -> None:
        with self._lock:
            record = self._events.get(event.event_id)
            if record is not None and record[0] == event:
                del self._events[event.event_id]

    def mark_terminal(self, event: RoadHazardEvent, now_ms: int | None = None) -> None:
        with self._lock:
            record = self._events.get(event.event_id)
            if record is not None and record[0] == event:
                self._events[event.event_id] = (event, self._clock() if now_ms is None else now_ms)
            self._cleanup_locked(self._clock() if now_ms is None else now_ms)

    def latest(self, event_id: str) -> RoadHazardEvent | None:
        with self._lock:
            self._cleanup_locked(self._clock())
            record = self._events.get(event_id)
            return None if record is None else record[0]


def _default_transport(url: str, token: str, payload: dict, timeout_s: float) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AIX-Token": token}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        parsed = json.loads(response.read().decode("utf-8"))
    if not isinstance(parsed, dict):
        raise ValueError("road hazard ACK must be a JSON object")
    return parsed


class RoadHazardSender:
    _DELAYS_S = (0.0, 0.2, 0.5, 1.0)

    def __init__(
        self, store: LatestFrameStore, states: ChainStateRepository, *, token: str,
        repository: RoadHazardRepository | None = None,
        transport: Callable[[str, str, dict, float], dict] | None = None,
        clock: Callable[[], int] | None = None,
        monotonic_clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        executor=None, executor_factory=None, max_pending: int = 32,
    ) -> None:
        if max_pending <= 0:
            raise ValueError("max_pending must be positive")
        self._store, self._states, self._token = store, states, token
        self._transport = transport or _default_transport
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._repository = repository or RoadHazardRepository(clock=self._clock)
        self._monotonic = monotonic_clock or time.monotonic
        self._sleep = sleep or time.sleep
        self._max_pending = max_pending
        self._lock = threading.RLock()
        self._external_executor = executor is not None
        self._executor_factory = executor_factory or (lambda: executor if executor is not None else ThreadPoolExecutor(max_workers=2, thread_name_prefix="road-hazard"))
        self._executor = executor or self._executor_factory()
        self._accepting = True
        self._jobs: dict[str, tuple[RoadHazardEvent, threading.Event, object]] = {}
        self._timers: dict[str, tuple[int, float]] = {}

    @property
    def store(self) -> LatestFrameStore:
        return self._store

    @property
    def states(self) -> ChainStateRepository:
        return self._states

    def start(self) -> None:
        with self._lock:
            if self._accepting:
                return
            if not self._external_executor:
                self._executor = self._executor_factory()
            self._accepting = True

    def stop(self) -> None:
        with self._lock:
            if not self._accepting and not self._jobs:
                return
            self._accepting = False
            executor, jobs = self._executor, list(self._jobs.values())
            self._jobs.clear()
            self._timers.clear()
        for event, stop_event, future in jobs:
            stop_event.set()
            cancel = getattr(future, "cancel", None)
            if callable(cancel):
                cancel()
            self._states.fail_road_hazard(event.device_id, event.event_id, "road hazard sender stopped", 0, self._clock())
            self._repository.mark_terminal(event, self._clock())
        if not self._external_executor:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                executor.shutdown(wait=False)

    def accept(self, event: RoadHazardEvent) -> bool:
        with self._lock:
            if not self._accepting:
                raise RoadHazardUnavailableError("road hazard sender is stopped")
            created = self._repository.accept(event)
            if not created:
                return False
            if len(self._jobs) >= self._max_pending:
                self._repository.discard(event)
                raise RoadHazardUnavailableError("road hazard sender queue is full")
            received_wall, received_monotonic = self._clock(), self._monotonic()
            stop_event, launch_gate = threading.Event(), threading.Event()
            try:
                future = self._executor.submit(self._run, event, stop_event, launch_gate)
            except RuntimeError as exc:
                self._repository.discard(event)
                raise RoadHazardUnavailableError("road hazard sender is unavailable") from exc
            self._jobs[event.event_id] = (event, stop_event, future)
            self._timers[event.event_id] = (received_wall, received_monotonic)
            self._states.begin_road_hazard(event.snapshot(), received_wall)
            launch_gate.set()
            return True

    def _run(self, event: RoadHazardEvent, stop_event: threading.Event, launch_gate: threading.Event) -> None:
        launch_gate.wait()
        try:
            with self._lock:
                timer = self._timers.get(event.event_id)
            if timer is None:
                return
            self.process(event, stop_event=stop_event, received_wall_ms=timer[0], received_monotonic=timer[1])
        except Exception as exc:
            self._fail(event, f"{exc.__class__.__name__}: {exc}", 0)
        finally:
            with self._lock:
                self._jobs.pop(event.event_id, None)
                self._timers.pop(event.event_id, None)
            self._repository.mark_terminal(event, self._clock())

    def process(
        self, event: RoadHazardEvent | dict, *, stop_event: threading.Event | None = None,
        received_wall_ms: int | None = None, received_monotonic: float | None = None,
    ) -> None:
        if isinstance(event, dict):
            event = RoadHazardEvent.from_payload(event)
        if received_wall_ms is None:
            received_wall_ms = self._clock()
            received_monotonic = self._monotonic()
            self._states.begin_road_hazard(event.snapshot(), received_wall_ms)
        stop_event = stop_event or threading.Event()
        if stop_event.is_set():
            self._fail(event, "road hazard sender stopped", 0)
            return
        frame = self._store.latest(event.device_id)
        if frame is None:
            self._fail(event, "no recent frame for device", 0)
            return
        age_ms = received_wall_ms - frame.received_ts_ms
        if age_ms < 0 or age_ms > 3000:
            self._fail(event, "latest frame is stale", 0)
            return
        if not isinstance(frame.source_ip, str) or not frame.source_ip:
            self._fail(event, "latest frame has no source address", 0)
            return

        attempts, last_error, last_remaining = 0, "delivery failed", event.ttl_ms
        for delay_s in self._DELAYS_S:
            self._sleep(delay_s)
            if stop_event.is_set():
                self._fail(event, "road hazard sender stopped", attempts)
                return
            elapsed_ms = max(0, int(round((self._monotonic() - received_monotonic) * 1000)))
            remaining_ttl_ms = min(last_remaining, event.ttl_ms - elapsed_ms)
            last_remaining = remaining_ttl_ms
            if remaining_ttl_ms <= 0:
                self._fail(event, "TTL expired before delivery", attempts)
                return
            attempts += 1
            started_ms = self._clock()
            try:
                ack = self._transport(
                    f"http://{frame.source_ip}:8080/road-hazard", self._token,
                    event.delivery_payload(frame.boot_id, remaining_ttl_ms), 0.5,
                )
            except urllib.error.HTTPError as exc:
                last_error = f"device HTTP {exc.code}"
                if 500 <= exc.code <= 599:
                    continue
                self._fail(event, last_error, attempts)
                return
            except (OSError, ValueError, json.JSONDecodeError, http.client.HTTPException) as exc:
                last_error = str(exc) or exc.__class__.__name__
                continue
            if stop_event.is_set():
                self._fail(event, "road hazard sender stopped", attempts)
                return
            latency_ms = max(0, self._clock() - started_ms)
            try:
                self._validate_ack(ack, event, frame.boot_id)
            except RoadHazardDeliveryError as exc:
                self._states.record_road_hazard_ack(event.device_id, event.event_id, None, latency_ms, attempts, str(exc), self._clock())
                return
            self._states.record_road_hazard_ack(event.device_id, event.event_id, ack, latency_ms, attempts, now_ms=self._clock())
            return
        self._fail(event, last_error, attempts)

    def _fail(self, event: RoadHazardEvent, error: str, attempts: int) -> None:
        self._states.fail_road_hazard(event.device_id, event.event_id, error, attempts, self._clock())

    @staticmethod
    def _validate_ack(ack: object, event: RoadHazardEvent, boot_id: str) -> None:
        if not isinstance(ack, dict):
            raise RoadHazardDeliveryError("road hazard ACK must be an object")
        if type(ack.get("version")) is not int or ack["version"] != 1:
            raise RoadHazardDeliveryError("ACK version mismatch")
        expected = {
            "type": "road_hazard_ack", "device_id": event.device_id, "boot_id": boot_id,
            "event_id": event.event_id, "severity": event.severity,
        }
        for key, value in expected.items():
            if ack.get(key) != value:
                raise RoadHazardDeliveryError(f"ACK {key} mismatch")
        for key in ("accepted", "duplicate"):
            if type(ack.get(key)) is not bool:
                raise RoadHazardDeliveryError(f"ACK {key} must be boolean")
        expires = ack.get("expires_in_ms")
        if type(expires) is not int or expires < 0:
            raise RoadHazardDeliveryError("ACK expires_in_ms is invalid")
        if not isinstance(ack.get("effective_rgb_pattern"), str):
            raise RoadHazardDeliveryError("ACK effective_rgb_pattern is invalid")
        if ack.get("voice_state") != "not_configured":
            raise RoadHazardDeliveryError("ACK voice_state is invalid")
        if not isinstance(ack.get("error"), str):
            raise RoadHazardDeliveryError("ACK error is invalid")
        if not ack["accepted"]:
            raise RoadHazardDeliveryError(ack["error"] or "device rejected road hazard")
