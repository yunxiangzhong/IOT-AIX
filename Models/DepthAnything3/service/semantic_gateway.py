from __future__ import annotations

import base64
import json
import re
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable, Sequence
from typing import Any

from frame_pipeline import FrameEnvelope


_ANALYSIS_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_REQUIRED_FIELDS = {
    "scene_type": str,
    "summary": str,
    "road_environment": str,
    "traffic_flow": str,
    "visibility": str,
    "changes": list,
    "confidence": (int, float),
    "uncertainty": str,
}
_FORBIDDEN_FIELDS = {
    "risk_score",
    "risk_band",
    "risk",
    "actuation",
    "action",
    "command",
    "recommendation",
}


class SemanticWindowScheduler:
    """Select three real frames spanning the newest analysis window."""

    def __init__(self, *, interval_ms: int = 6_000, capacity: int = 8) -> None:
        if interval_ms <= 0 or capacity < 3:
            raise ValueError("invalid semantic window configuration")
        self._interval_ms = interval_ms
        self._frames: deque[FrameEnvelope] = deque(maxlen=capacity)
        self._last_dispatch_ms: int | None = None
        self._stream_key: tuple[str, str] | None = None

    @property
    def buffered_count(self) -> int:
        return len(self._frames)

    def offer(
        self, frame: FrameEnvelope
    ) -> tuple[FrameEnvelope, FrameEnvelope, FrameEnvelope] | None:
        if self._stream_key != frame.stream_key:
            self._frames.clear()
            self._last_dispatch_ms = None
            self._stream_key = frame.stream_key
        self._frames.append(frame)
        if len(self._frames) < 3:
            return None

        if self._last_dispatch_ms is None:
            if frame.received_ts_ms - self._frames[0].received_ts_ms < self._interval_ms:
                return None
        elif frame.received_ts_ms - self._last_dispatch_ms <= self._interval_ms:
            return None

        target_start = frame.received_ts_ms - self._interval_ms
        target_mid = frame.received_ts_ms - self._interval_ms // 2
        candidates = list(self._frames)
        start = min(candidates, key=lambda item: abs(item.received_ts_ms - target_start))
        middle_candidates = [
            item for item in candidates if item.frame_seq not in {start.frame_seq, frame.frame_seq}
        ]
        if not middle_candidates:
            return None
        middle = min(
            middle_candidates, key=lambda item: abs(item.received_ts_ms - target_mid)
        )
        selected = tuple(sorted((start, middle, frame), key=lambda item: item.received_ts_ms))
        self._last_dispatch_ms = frame.received_ts_ms
        return selected


class SemanticGatewayClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "doubao-seed-1.6-flash",
        base_url: str = "https://ai-gateway.vei.volces.com/v1",
        timeout_s: float = 20.0,
        completion: Callable[[dict[str, Any]], str] | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("VEI_API_KEY is required")
        self._api_key = api_key
        self.model = model
        self.base_url = base_url
        self.timeout_s = timeout_s
        self._completion = completion

    def analyze(self, frames: Sequence[FrameEnvelope]) -> dict[str, Any]:
        if len(frames) != 3:
            raise ValueError("semantic analysis requires exactly three frames")
        request = {
            "model": self.model,
            "prompt": (
                "分析按时间排列的三张真实视频关键帧。仅描述场景语义与跨帧变化，"
                "不要输出风险分数、控制命令、执行建议或气动建议。"
            ),
            "images": [
                "data:image/jpeg;base64,"
                + base64.b64encode(item.jpeg).decode("ascii")
                for item in frames
            ],
        }
        raw = (
            self._completion(request)
            if self._completion is not None
            else self._openai_completion(request)
        )
        return self._parse_result(raw)

    def _openai_completion(self, request: dict[str, Any]) -> str:
        from openai import OpenAI

        client = OpenAI(
            base_url=self.base_url,
            api_key=self._api_key,
            timeout=self.timeout_s,
        )
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    request["prompt"]
                    + '\n只返回 JSON：{"scene_type":字符串,"summary":中文字符串,'
                    '"road_environment":字符串,"traffic_flow":字符串,'
                    '"visibility":字符串,"changes":字符串数组,'
                    '"confidence":0到1数字,"uncertainty":中文字符串}'
                ),
            }
        ]
        content.extend(
            {"type": "image_url", "image_url": {"url": image}}
            for image in request["images"]
        )
        response = client.chat.completions.create(
            model=request["model"],
            messages=[{"role": "user", "content": content}],
            max_tokens=500,
            temperature=0,
        )
        text = response.choices[0].message.content
        if not isinstance(text, str):
            raise ValueError("semantic response has no text content")
        return text

    @staticmethod
    def _parse_result(raw: str) -> dict[str, Any]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("semantic response must be a JSON object")
        forbidden = sorted(_FORBIDDEN_FIELDS.intersection(payload))
        if forbidden:
            raise ValueError(f"forbidden semantic fields: {', '.join(forbidden)}")
        missing = [key for key in _REQUIRED_FIELDS if key not in payload]
        if missing:
            raise ValueError(f"missing semantic fields: {', '.join(missing)}")
        for key, expected_type in _REQUIRED_FIELDS.items():
            if not isinstance(payload[key], expected_type):
                raise ValueError(f"invalid semantic field type: {key}")
        if isinstance(payload["confidence"], bool):
            raise ValueError("invalid semantic confidence")
        confidence = float(payload["confidence"])
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("semantic confidence must be between 0 and 1")
        if not all(isinstance(item, str) for item in payload["changes"]):
            raise ValueError("semantic changes must contain strings")
        payload["confidence"] = confidence
        return payload


class SemanticResultCache:
    def __init__(self, *, capacity: int = 20) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._capacity = capacity
        self._items: OrderedDict[str, tuple[dict[str, Any], tuple[bytes, ...]]] = (
            OrderedDict()
        )

    @staticmethod
    def _validate_id(analysis_id: str) -> None:
        if not _ANALYSIS_ID_RE.fullmatch(analysis_id):
            raise KeyError(analysis_id)

    def put(
        self,
        analysis_id: str,
        record: dict[str, Any],
        frames: Sequence[FrameEnvelope],
    ) -> None:
        self._validate_id(analysis_id)
        if len(frames) != 3:
            raise ValueError("semantic cache requires exactly three frames")
        self._items[analysis_id] = (
            dict(record),
            tuple(bytes(item.jpeg) for item in frames),
        )
        self._items.move_to_end(analysis_id)
        while len(self._items) > self._capacity:
            self._items.popitem(last=False)

    def get(self, analysis_id: str) -> dict[str, Any] | None:
        self._validate_id(analysis_id)
        item = self._items.get(analysis_id)
        return None if item is None else dict(item[0])

    def keyframe(self, analysis_id: str, index: int) -> bytes:
        self._validate_id(analysis_id)
        if index not in (1, 2, 3):
            raise KeyError(index)
        try:
            return self._items[analysis_id][1][index - 1]
        except KeyError:
            raise KeyError(analysis_id) from None


class SemanticAnalysisWorker:
    """Independent latest-window worker; pending work is replaced, never queued."""

    def __init__(
        self,
        *,
        client: SemanticGatewayClient,
        cache: SemanticResultCache,
        record: Callable[[str, dict[str, Any]], None],
        indicator: Callable[[FrameEnvelope, dict[str, Any]], dict[str, Any]],
        interval_ms: int = 6_000,
    ) -> None:
        self._client = client
        self._cache = cache
        self._record = record
        self._indicator = indicator
        self._scheduler = SemanticWindowScheduler(interval_ms=interval_ms)
        self._condition = threading.Condition()
        self._pending: tuple[FrameEnvelope, FrameEnvelope, FrameEnvelope] | None = None
        self._stop = False
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="aix-semantic-analysis", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        with self._condition:
            self._stop = True
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3.0)

    def offer(self, frame: FrameEnvelope) -> None:
        window = self._scheduler.offer(frame)
        if window is None:
            return
        with self._condition:
            self._pending = window
            self._condition.notify()

    def _take(self) -> tuple[FrameEnvelope, FrameEnvelope, FrameEnvelope] | None:
        with self._condition:
            while self._pending is None and not self._stop:
                self._condition.wait(timeout=0.2)
            if self._stop:
                return None
            result = self._pending
            self._pending = None
            return result

    def _run(self) -> None:
        while True:
            frames = self._take()
            if frames is None:
                return
            first, _, last = frames
            analysis_id = (
                f"sem-{last.boot_id}-{last.frame_seq}-{last.received_ts_ms}"
            )
            started = time.perf_counter()
            record: dict[str, Any] = {
                "device_id": last.device_id,
                "boot_id": last.boot_id,
                "status": "running",
                "analysis_id": analysis_id,
                "model": self._client.model,
                "frame_seqs": [item.frame_seq for item in frames],
                "capture_ts_ms": [item.capture_ts_ms for item in frames],
                "started_ts_ms": int(time.time() * 1000),
                "latency_ms": None,
                "result": None,
                "error": "",
                "rgb_delivery": {
                    "state": "waiting",
                    "flashed": False,
                    "effective_rgb_pattern": "",
                },
            }
            try:
                record["result"] = self._client.analyze(frames)
                record["status"] = "ready"
                payload = {
                    "type": "semantic_indicator",
                    "version": 1,
                    "device_id": last.device_id,
                    "boot_id": last.boot_id,
                    "analysis_id": analysis_id,
                    "frame_seq": last.frame_seq,
                }
                try:
                    ack = self._indicator(last, payload)
                    record["rgb_delivery"] = {
                        "state": "confirmed",
                        "flashed": bool(ack.get("flashed", False)),
                        "suppressed": bool(ack.get("suppressed", False)),
                        "reason": str(ack.get("reason", "")),
                        "effective_rgb_pattern": str(
                            ack.get("effective_rgb_pattern", "")
                        ),
                    }
                except Exception as exc:
                    record["rgb_delivery"] = {
                        "state": "failed",
                        "flashed": False,
                        "effective_rgb_pattern": "",
                        "error": str(exc),
                    }
            except Exception as exc:
                record["status"] = "error"
                record["error"] = str(exc)
            record["latency_ms"] = round(
                (time.perf_counter() - started) * 1000.0, 2
            )
            record["completed_ts_ms"] = int(time.time() * 1000)
            self._cache.put(analysis_id, record, frames)
            self._record(first.device_id, record)
