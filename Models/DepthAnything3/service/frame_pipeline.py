from __future__ import annotations

import json
import math
import threading
import time
import urllib.request
from collections import defaultdict, deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class FrameEnvelope:
    device_id: str
    boot_id: str
    frame_seq: int
    capture_ts_ms: int
    source_ip: str
    jpeg: bytes
    received_ts_ms: int

    @property
    def stream_key(self) -> tuple[str, str]:
        return self.device_id, self.boot_id


@dataclass
class VoicePromptState:
    risk_band: str = "low"
    last_prompt_ms: int | None = None


class VoicePromptPolicy:
    """Adds idempotent DFPlayer prompts per device boot stream.

    A risk escalation is prompt-worthy immediately. A steady band is repeated
    only after the configured interval; a downgrade starts a new cooldown and
    low clears the current cycle.
    """

    _TRACKS = {"attention": 1, "high": 2, "critical": 3}

    def __init__(self, repeat_interval_ms: int = 10_000) -> None:
        self._repeat_interval_ms = repeat_interval_ms
        self._states: dict[tuple[str, str], VoicePromptState] = {}

    def enrich(self, frame: FrameEnvelope, risk: dict, *, now_ms: int) -> dict:
        payload = dict(risk)
        band = str(payload.get("risk_band", "low"))
        state = self._states.setdefault(frame.stream_key, VoicePromptState())
        track = self._TRACKS.get(band)
        if track is None:
            state.risk_band = "low"
            state.last_prompt_ms = None
            return payload

        previous_track = self._TRACKS.get(state.risk_band, 0)
        should_prompt = (
            previous_track == 0
            or track > previous_track
            or (track == previous_track and state.last_prompt_ms is not None and
                now_ms - state.last_prompt_ms >= self._repeat_interval_ms)
        )
        state.risk_band = band
        if should_prompt:
            state.last_prompt_ms = now_ms
            payload["voice_prompt"] = {
                "command_id": f"{frame.boot_id}:{frame.frame_seq}:{track}",
                "track": track,
            }
        elif track < previous_track:
            # A downgrade never interrupts the current announcement, but its
            # own persistent risk can be announced after a full cooldown.
            state.last_prompt_ms = now_ms
        return payload


class LatestFrameStore:
    """Keeps one pending frame per boot stream and one UI snapshot per device."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._pending: dict[tuple[str, str], FrameEnvelope] = {}
        self._latest: dict[str, FrameEnvelope] = {}
        self._processed: dict[str, FrameEnvelope] = {}

    def put(self, item: FrameEnvelope) -> bool:
        with self._condition:
            replaced = item.stream_key in self._pending
            self._pending[item.stream_key] = item
            self._latest[item.device_id] = item
            self._condition.notify()
            return replaced

    def take(self, timeout: float | None = None) -> FrameEnvelope | None:
        with self._condition:
            if not self._pending:
                self._condition.wait(timeout)
            if not self._pending:
                return None
            key, item = max(self._pending.items(), key=lambda pair: pair[1].received_ts_ms)
            del self._pending[key]
            return item

    def latest(self, device_id: str) -> FrameEnvelope | None:
        with self._condition:
            return self._latest.get(device_id)

    def commit_processed(self, item: FrameEnvelope) -> None:
        with self._condition:
            current = self._processed.get(item.device_id)
            if current is None or current.boot_id != item.boot_id or item.frame_seq >= current.frame_seq:
                self._processed[item.device_id] = item

    def latest_processed(self, device_id: str) -> FrameEnvelope | None:
        with self._condition:
            return self._processed.get(device_id)

    def is_latest(self, item: FrameEnvelope) -> bool:
        latest = self.latest(item.device_id)
        return latest is not None and latest.boot_id == item.boot_id and latest.frame_seq == item.frame_seq

    def wake(self) -> None:
        with self._condition:
            self._condition.notify_all()


class ChainStateRepository:
    def __init__(self, model_state: str = "loading") -> None:
        self._lock = threading.Lock()
        self._states: dict[str, dict] = {}
        self._arrivals: dict[str, deque[int]] = defaultdict(deque)
        self._model_state = model_state
        self._model_error = ""
        self._model_name = "DA3-SMALL"
        self._detector_name = ""
        self._backend = "cuda"
        self._gpu = "cuda"

    def _base(self, device_id: str) -> dict:
        return {
            "type": "chain_state",
            "version": 1,
            "revision": 0,
            "device_id": device_id,
            "boot_id": "",
            "camera": {"state": "unknown"},
            "upload": {"state": "waiting", "last_frame_seq": -1, "fps": 0.0, "frame_age_ms": None, "accepted_frames": 0, "queue_replaced": 0},
            "model": {
                "state": self._model_state,
                "name": self._model_name,
                "detector": self._detector_name,
                "backend": self._backend,
                "latency_ms": None,
                "gpu": self._gpu,
                "error": self._model_error,
                "valid_results": 0,
            },
            "callback": {"state": "waiting", "latency_ms": None, "attempts": 0, "confirmed_count": 0, "failed_count": 0},
            "risk": {"valid": False, "score": 0, "band": "low", "reason": ""},
            "action": {"confirmed": False, "state": "loading", "rgb_pattern": "blue_blink_1hz", "frame_seq": -1},
            "road_hazard": {
                "event_id": "",
                "roadside_capture": {"state": "waiting"},
                "cloud_recognition": {"state": "waiting"},
                "arrival_prediction": {"state": "waiting"},
                "delivery": {"state": "waiting"},
                "ack": {"state": "waiting", "payload": None},
                "attempts": 0,
                "network_latency_ms": None,
                "effective_rgb_pattern": "",
                "error": "",
                "updated_ts_ms": 0,
            },
            "display": {
                "ready": False,
                "url": "/v1/frame/processed.jpg",
                "boot_id": "",
                "frame_seq": -1,
                "capture_ts_ms": -1,
                "detections": [],
            },
            "last_error": "",
            "server_ts_ms": 0,
        }

    @staticmethod
    def _touch(state: dict) -> None:
        state["revision"] = int(state.get("revision", 0)) + 1

    def record_frame(self, item: FrameEnvelope, queue_replaced: bool = False) -> None:
        with self._lock:
            state = self._states.setdefault(item.device_id, self._base(item.device_id))
            arrivals = self._arrivals[item.device_id]
            arrivals.append(item.received_ts_ms)
            cutoff = item.received_ts_ms - 10_000
            while arrivals and arrivals[0] < cutoff:
                arrivals.popleft()
            span_ms = max(1, arrivals[-1] - arrivals[0]) if len(arrivals) > 1 else 0
            fps = ((len(arrivals) - 1) * 1000.0 / span_ms) if span_ms else 0.0
            state["boot_id"] = item.boot_id
            state["camera"] = {"state": "streaming", "capture_ts_ms": item.capture_ts_ms}
            state["upload"].update(
                state="healthy",
                last_frame_seq=item.frame_seq,
                received_ts_ms=item.received_ts_ms,
                fps=round(fps, 2),
            )
            state["upload"]["accepted_frames"] += 1
            if queue_replaced:
                state["upload"]["queue_replaced"] += 1
            state["model"].update(state=self._model_state, error=self._model_error)
            self._touch(state)

    def set_model(
        self,
        model_state: str,
        *,
        error: str = "",
        model: str = "DA3-SMALL",
        detector: str = "",
        backend: str = "cuda",
        gpu: str = "cuda",
    ) -> None:
        with self._lock:
            self._model_state = model_state
            self._model_error = error
            self._model_name = model
            self._detector_name = detector
            self._backend = backend
            self._gpu = gpu
            for state in self._states.values():
                state["model"].update(
                    state=model_state,
                    error=error,
                    name=model,
                    detector=detector,
                    backend=backend,
                    gpu=gpu,
                )
                if error:
                    state["last_error"] = error
                self._touch(state)

    def record_risk(self, item: FrameEnvelope, risk: dict, latency_ms: float) -> None:
        with self._lock:
            state = self._states.setdefault(item.device_id, self._base(item.device_id))
            state["model"].update(state="ready", latency_ms=round(latency_ms, 2), error="")
            state["model"]["valid_results"] = int(state["model"].get("valid_results", 0)) + 1
            state["risk"] = {
                "valid": bool(risk.get("valid")),
                "score": int(risk["risk_score"]),
                "band": risk["risk_band"],
                "reason": risk.get("reason", ""),
                "dominant_class": risk.get("dominant_class", ""),
                "frame_seq": item.frame_seq,
            }
            state["display"] = {
                "ready": True,
                "url": "/v1/frame/processed.jpg",
                "boot_id": item.boot_id,
                "frame_seq": item.frame_seq,
                "capture_ts_ms": item.capture_ts_ms,
                "detections": deepcopy(risk.get("detections", [])),
            }
            self._touch(state)

    def record_callback(self, item: FrameEnvelope, ack: dict | None, latency_ms: float, attempts: int, error: str = "") -> None:
        with self._lock:
            state = self._states.setdefault(item.device_id, self._base(item.device_id))
            state["callback"] = {
                "state": "confirmed" if ack else "failed",
                "latency_ms": round(latency_ms, 2),
                "attempts": attempts,
                "error": error,
                "confirmed_count": int(state["callback"].get("confirmed_count", 0)) + (1 if ack else 0),
                "failed_count": int(state["callback"].get("failed_count", 0)) + (0 if ack else 1),
            }
            if ack:
                state["action"] = {
                    "confirmed": True,
                    "state": ack["action_state"],
                    "rgb_pattern": ack["rgb_pattern"],
                    "frame_seq": ack["frame_seq"],
                    "stale": bool(ack.get("stale", False)),
                    "e2e_latency_ms": ack.get("e2e_latency_ms"),
                }
                state["last_error"] = ""
            elif error:
                state["last_error"] = error
            self._touch(state)

    def begin_road_hazard(self, event: dict, now_ms: int) -> None:
        with self._lock:
            state = self._states.setdefault(event["device_id"], self._base(event["device_id"]))
            state["road_hazard"] = {
                "event_id": event["event_id"],
                "roadside_capture": {"state": "completed"},
                "cloud_recognition": {"state": "completed"},
                "arrival_prediction": {"state": "completed"},
                "delivery": {"state": "active"},
                "ack": {"state": "waiting", "payload": None},
                "attempts": 0,
                "network_latency_ms": None,
                "effective_rgb_pattern": "",
                "error": "",
                "updated_ts_ms": now_ms,
            }
            self._touch(state)

    def fail_road_hazard(self, device_id: str, event_id: str, error: str, attempts: int, now_ms: int) -> bool:
        with self._lock:
            state = self._states.setdefault(device_id, self._base(device_id))
            hazard = state["road_hazard"]
            if hazard.get("event_id") != event_id:
                return False
            if hazard["ack"].get("state") in {"completed", "failed"}:
                return False
            hazard["delivery"] = {"state": "failed"}
            hazard["ack"] = {"state": "failed", "payload": None}
            hazard["attempts"] = attempts
            hazard["error"] = error
            hazard["updated_ts_ms"] = now_ms
            state["last_error"] = error
            self._touch(state)
            return True

    def record_road_hazard_ack(self, device_id: str, event_id: str, ack: dict | None, latency_ms: float, attempts: int, error: str = "", now_ms: int | None = None) -> bool:
        with self._lock:
            state = self._states.setdefault(device_id, self._base(device_id))
            hazard = state["road_hazard"]
            if hazard.get("event_id") != event_id:
                return False
            if hazard["ack"].get("state") in {"completed", "failed"}:
                return False
            hazard["delivery"] = {"state": "completed" if ack is not None else "failed"}
            hazard["ack"] = {"state": "completed" if ack is not None else "failed", "payload": deepcopy(ack) if ack is not None else None}
            hazard["attempts"] = attempts
            hazard["network_latency_ms"] = round(latency_ms, 2)
            hazard["effective_rgb_pattern"] = ack.get("effective_rgb_pattern", "") if ack else ""
            hazard["error"] = error
            hazard["updated_ts_ms"] = int(time.time() * 1000) if now_ms is None else now_ms
            if error:
                state["last_error"] = error
            self._touch(state)
            return True

    def latest(self, device_id: str, now_ms: int | None = None) -> dict | None:
        with self._lock:
            state = self._states.get(device_id)
            if state is None:
                return None
            result = deepcopy(state)
        current_ms = int(time.time() * 1000) if now_ms is None else now_ms
        received = result["upload"].get("received_ts_ms")
        result["upload"]["frame_age_ms"] = max(0, current_ms - received) if received is not None else None
        result["server_ts_ms"] = current_ms
        return result

    def health(self) -> dict:
        with self._lock:
            return {
                "model_state": self._model_state,
                "model_error": self._model_error,
                "model": self._model_name,
                "detector": self._detector_name,
                "backend": self._backend,
                "gpu": self._gpu,
            }


def _http_transport(url: str, token: str, payload: dict, timeout_s: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AIX-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        if response.status != 200:
            raise OSError(f"callback returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


class RiskCallbackClient:
    def __init__(
        self,
        *,
        token: str,
        transport: Callable[[str, str, dict, float], dict] = _http_transport,
        retry_delays_s: tuple[float, ...] = (0.0, 0.2, 0.5, 1.0),
        timeout_s: float = 0.5,
    ) -> None:
        self._token = token
        self._transport = transport
        self._retry_delays_s = retry_delays_s
        self._timeout_s = timeout_s
        self.last_attempts = 0
        self.last_error = ""

    @staticmethod
    def _voice_ack_matches_prompt(prompt: dict, voice_ack: object) -> bool:
        if not isinstance(voice_ack, dict):
            return False
        command_id = prompt.get("command_id")
        track = prompt.get("track")
        if not isinstance(command_id, str) or type(track) is not int:
            return False
        if voice_ack.get("requested") is not True:
            return False
        ack_track = voice_ack.get("track")
        if voice_ack.get("command_id") != command_id or type(ack_track) is not int or ack_track != track:
            return False
        accepted = voice_ack.get("accepted")
        duplicate = voice_ack.get("duplicate")
        status = voice_ack.get("status")
        if type(accepted) is not bool or type(duplicate) is not bool:
            return False
        expected = {
            "queued": (True, False),
            "duplicate": (True, True),
            "suppressed": (False, False),
            "unavailable": (False, False),
            "rejected": (False, False),
        }.get(status)
        return expected is not None and (accepted, duplicate) == expected

    def send(self, frame: FrameEnvelope, payload: dict, *, is_current: Callable[[], bool]) -> dict | None:
        self.last_attempts = 0
        self.last_error = ""
        url = f"http://{frame.source_ip}:8080/risk"
        for delay_s in self._retry_delays_s:
            if not is_current():
                self.last_error = "callback superseded by a newer frame"
                return None
            if delay_s:
                time.sleep(delay_s)
                if not is_current():
                    self.last_error = "callback superseded by a newer frame"
                    return None
            self.last_attempts += 1
            try:
                ack = self._transport(url, self._token, payload, self._timeout_s)
                if (
                    ack.get("type") != "action_ack"
                    or ack.get("version") != 1
                    or ack.get("frame_seq") != frame.frame_seq
                    or ack.get("accepted") is not True
                    or not isinstance(ack.get("action_state"), str)
                    or not isinstance(ack.get("rgb_pattern"), str)
                ):
                    raise ValueError("invalid or mismatched action_ack")
                if "voice_prompt" in payload and not self._voice_ack_matches_prompt(
                    payload["voice_prompt"], ack.get("voice_ack")
                ):
                    raise ValueError("invalid or mismatched voice_ack for requested voice prompt")
                e2e_latency_ms = ack.get("e2e_latency_ms")
                if e2e_latency_ms is not None and (
                    isinstance(e2e_latency_ms, bool)
                    or not isinstance(e2e_latency_ms, (int, float))
                    or not math.isfinite(e2e_latency_ms)
                    or e2e_latency_ms < 0
                ):
                    raise ValueError("action_ack e2e_latency_ms must be finite and non-negative")
                return ack
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self.last_error = str(exc)
        return None


class AnalysisWorker:
    def __init__(
        self,
        store: LatestFrameStore,
        states: ChainStateRepository,
        callback: RiskCallbackClient,
        analyzer=None,
    ) -> None:
        self._store = store
        self._states = states
        self._callback = callback
        self._analyzer = analyzer
        self._voice_policy = VoicePromptPolicy()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def set_analyzer(self, analyzer) -> None:
        with self._lock:
            self._analyzer = analyzer
        self._states.set_model(
            "ready",
            model=getattr(analyzer, "depth_model_name", "DA3-SMALL"),
            detector=getattr(analyzer, "detector_model_name", ""),
            backend=getattr(analyzer, "backend", "cuda"),
            gpu=getattr(analyzer, "device", "cuda"),
        )
        self._store.wake()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="aix-analysis", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._store.wake()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                analyzer = self._analyzer
            if analyzer is None:
                self._stop.wait(0.05)
                continue
            item = self._store.take(timeout=0.1)
            if item is None:
                continue
            started = time.perf_counter()
            try:
                risk = analyzer.analyze_jpeg(
                    item.jpeg,
                    frame_seq=item.frame_seq,
                    capture_ts_ms=item.capture_ts_ms,
                    session_id=f"{item.device_id}:{item.boot_id}",
                )
                risk.update(device_id=item.device_id, boot_id=item.boot_id)
                self._store.commit_processed(item)
                self._states.record_risk(item, risk, (time.perf_counter() - started) * 1000.0)
                callback_payload = self._voice_policy.enrich(item, risk, now_ms=int(time.time() * 1000))
                callback_started = time.perf_counter()
                ack = self._callback.send(item, callback_payload, is_current=lambda: self._store.is_latest(item))
                self._states.record_callback(
                    item,
                    ack,
                    (time.perf_counter() - callback_started) * 1000.0,
                    self._callback.last_attempts,
                    self._callback.last_error,
                )
            except Exception as exc:
                self._states.set_model("error", error=str(exc))
