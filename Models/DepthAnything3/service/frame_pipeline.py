from __future__ import annotations

import json
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
        self._gpu = "cuda"

    def _base(self, device_id: str) -> dict:
        return {
            "type": "chain_state",
            "version": 1,
            "device_id": device_id,
            "boot_id": "",
            "camera": {"state": "unknown"},
            "upload": {"state": "waiting", "last_frame_seq": -1, "fps": 0.0, "frame_age_ms": None, "accepted_frames": 0, "queue_replaced": 0},
            "model": {"state": self._model_state, "latency_ms": None, "gpu": "cuda", "error": self._model_error, "valid_results": 0},
            "callback": {"state": "waiting", "latency_ms": None, "attempts": 0, "confirmed_count": 0, "failed_count": 0},
            "risk": {"valid": False, "score": 0, "band": "low", "reason": ""},
            "action": {"confirmed": False, "state": "loading", "rgb_pattern": "blue_blink_1hz", "frame_seq": -1},
            "last_error": "",
            "server_ts_ms": 0,
        }

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

    def set_model(self, model_state: str, *, error: str = "", model: str = "DA3-SMALL", gpu: str = "cuda") -> None:
        with self._lock:
            self._model_state = model_state
            self._model_error = error
            self._model_name = model
            self._gpu = gpu
            for state in self._states.values():
                state["model"].update(state=model_state, error=error, name=model, gpu=gpu)
                if error:
                    state["last_error"] = error

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
                }
                state["last_error"] = ""
            elif error:
                state["last_error"] = error

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
                if "voice_prompt" in payload and not isinstance(ack.get("voice_ack"), dict):
                    raise ValueError("missing voice_ack for requested voice prompt")
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
