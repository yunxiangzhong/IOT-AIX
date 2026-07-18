from __future__ import annotations

import json
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


_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}$")
_SEVERITIES = {"attention", "high", "critical"}
_DIRECTIONS = {"left", "right", "front", "rear"}
_FIELDS = (
    "event_id", "device_id", "camera_id", "intersection_id", "direction",
    "object_type", "eta_ms", "severity", "ttl_ms", "simulated", "message_code",
)


def _positive_int(payload: dict, field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
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
        values = {}
        for field in ("event_id", "device_id", "camera_id", "intersection_id", "object_type", "message_code"):
            value = payload.get(field)
            if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
                raise RoadHazardValidationError(f"{field} must be 1-64 URL-safe characters")
            values[field] = value
        direction = payload.get("direction")
        if direction not in _DIRECTIONS:
            raise RoadHazardValidationError("direction is invalid")
        severity = payload.get("severity")
        if severity not in _SEVERITIES:
            raise RoadHazardValidationError("severity is invalid")
        simulated = payload.get("simulated")
        if not isinstance(simulated, bool):
            raise RoadHazardValidationError("simulated must be boolean")
        return cls(
            **values, direction=direction, severity=severity, simulated=simulated,
            eta_ms=_positive_int(payload, "eta_ms"), ttl_ms=_positive_int(payload, "ttl_ms"),
        )

    def content(self) -> dict:
        return {field: getattr(self, field) for field in _FIELDS}

    def snapshot(self) -> dict:
        return dict(self.content())

    def delivery_payload(self, boot_id: str, remaining_ttl_ms: int) -> dict:
        return {"type": "road_hazard", "version": 1, **self.content(), "ttl_ms": remaining_ttl_ms, "boot_id": boot_id}


class RoadHazardRepository:
    """Thread-safe event-id idempotency registry."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: dict[str, RoadHazardEvent] = {}

    def accept(self, event: RoadHazardEvent) -> bool:
        with self._lock:
            previous = self._events.get(event.event_id)
            if previous is None:
                self._events[event.event_id] = event
                return True
            if previous == event:
                return False
            raise RoadHazardConflictError("event_id already exists with different content")


def _default_transport(url: str, token: str, payload: dict, timeout_s: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AIX-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        raw = response.read().decode("utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("road hazard ACK must be a JSON object")
    return parsed


class RoadHazardSender:
    _DELAYS_S = (0.0, 0.2, 0.5, 1.0)

    def __init__(
        self,
        store: LatestFrameStore,
        states: ChainStateRepository,
        *,
        token: str,
        repository: RoadHazardRepository | None = None,
        transport: Callable[[str, str, dict, float], dict] | None = None,
        clock: Callable[[], int] | None = None,
        sleep: Callable[[float], None] | None = None,
        executor=None,
    ) -> None:
        self._store = store
        self._states = states
        self._token = token
        self._repository = repository or RoadHazardRepository()
        self._transport = transport or _default_transport
        self._clock = clock or (lambda: int(time.time() * 1000))
        self._sleep = sleep or time.sleep
        self._executor = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="road-hazard")
        self._owns_executor = executor is None
        self._received_ts_ms: dict[str, int] = {}

    @property
    def store(self) -> LatestFrameStore:
        return self._store

    @property
    def states(self) -> ChainStateRepository:
        return self._states

    def start(self) -> None:
        return None

    def stop(self) -> None:
        if self._owns_executor:
            self._executor.shutdown(wait=True)

    def accept(self, event: RoadHazardEvent) -> bool:
        created = self._repository.accept(event)
        if created:
            received_ms = self._clock()
            self._received_ts_ms[event.event_id] = received_ms
            self._states.begin_road_hazard(event.snapshot(), received_ms)
            self._executor.submit(self.process, event)
        return created

    def process(self, event: RoadHazardEvent | dict) -> None:
        if isinstance(event, dict):
            event = RoadHazardEvent.from_payload(event)
            self._states.begin_road_hazard(event.snapshot(), self._clock())
        received_ms = self._received_ts_ms.get(event.event_id, self._clock())
        frame = self._store.latest(event.device_id)
        if frame is None:
            self._fail(event, "no recent frame for device", 0)
            return
        age_ms = received_ms - frame.received_ts_ms
        if age_ms < 0 or age_ms > 3000:
            self._fail(event, "latest frame is stale", 0)
            return
        if not isinstance(frame.source_ip, str) or not frame.source_ip:
            self._fail(event, "latest frame has no source address", 0)
            return

        attempts = 0
        for delay_s in self._DELAYS_S:
            self._sleep(delay_s)
            now_ms = self._clock()
            remaining_ttl_ms = event.ttl_ms - (now_ms - received_ms)
            if remaining_ttl_ms <= 0:
                self._fail(event, "TTL expired before delivery", attempts)
                return
            attempts += 1
            payload = event.delivery_payload(frame.boot_id, remaining_ttl_ms)
            started_ms = self._clock()
            try:
                ack = self._transport(f"http://{frame.source_ip}:8080/road-hazard", self._token, payload, 0.5)
            except urllib.error.HTTPError as exc:
                if 500 <= exc.code <= 599:
                    continue
                self._fail(event, f"device HTTP {exc.code}", attempts)
                return
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc) or exc.__class__.__name__
                continue
            latency_ms = max(0, self._clock() - started_ms)
            try:
                self._validate_ack(ack, event, frame.boot_id)
            except RoadHazardDeliveryError as exc:
                self._states.record_road_hazard_ack(event.device_id, event.event_id, None, latency_ms, attempts, str(exc), self._clock())
                return
            self._states.record_road_hazard_ack(event.device_id, event.event_id, ack, latency_ms, attempts, now_ms=self._clock())
            return
        self._fail(event, locals().get("last_error", "delivery failed"), attempts)

    def _fail(self, event: RoadHazardEvent, error: str, attempts: int) -> None:
        self._states.fail_road_hazard(event.device_id, event.event_id, error, attempts, self._clock())

    @staticmethod
    def _validate_ack(ack: object, event: RoadHazardEvent, boot_id: str) -> None:
        if not isinstance(ack, dict):
            raise RoadHazardDeliveryError("road hazard ACK must be an object")
        expected = {
            "type": "road_hazard_ack", "version": 1, "device_id": event.device_id,
            "boot_id": boot_id, "event_id": event.event_id, "severity": event.severity,
        }
        for key, value in expected.items():
            if ack.get(key) != value:
                raise RoadHazardDeliveryError(f"ACK {key} mismatch")
        for key in ("accepted", "duplicate"):
            if not isinstance(ack.get(key), bool):
                raise RoadHazardDeliveryError(f"ACK {key} must be boolean")
        expires = ack.get("expires_in_ms")
        if isinstance(expires, bool) or not isinstance(expires, int) or expires < 0:
            raise RoadHazardDeliveryError("ACK expires_in_ms is invalid")
        if not isinstance(ack.get("effective_rgb_pattern"), str):
            raise RoadHazardDeliveryError("ACK effective_rgb_pattern is invalid")
        if ack.get("voice_state") != "not_configured":
            raise RoadHazardDeliveryError("ACK voice_state is invalid")
        if not isinstance(ack.get("error"), str):
            raise RoadHazardDeliveryError("ACK error is invalid")
        if not ack["accepted"]:
            raise RoadHazardDeliveryError(ack["error"] or "device rejected road hazard")
