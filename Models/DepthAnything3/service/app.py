from __future__ import annotations

import re
import json
import urllib.request
import threading
import time
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Callable, Protocol

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

from frame_pipeline import AnalysisWorker, ChainStateRepository, FrameEnvelope, LatestFrameStore, RiskCallbackClient
from inference import PredictionSummary
from operating_mode import OperatingModeController
from pneumatic_proxy import PneumaticProtocolError, PneumaticProxy, PneumaticProxyError, StaleDeviceError
from road_hazard import RoadHazardConflictError, RoadHazardEvent, RoadHazardSender, RoadHazardUnavailableError, RoadHazardValidationError
from schemas import build_vision_depth_response
from semantic_gateway import (
    SemanticAnalysisWorker,
    SemanticGatewayClient,
    SemanticResultCache,
)


class InferenceEngine(Protocol):
    model_name: str
    device: str

    def infer_jpeg(self, image_bytes: bytes) -> PredictionSummary: ...


def _is_jpeg(image_bytes: bytes) -> bool:
    return len(image_bytes) >= 4 and image_bytes[:2] == b"\xff\xd8" and image_bytes[-2:] == b"\xff\xd9"


def _http_get(url: str, timeout_s: float) -> dict:
    """Simple GET for /healthz probing — no auth token needed."""
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        if resp.status != 200:
            raise OSError(f"health check returned HTTP {resp.status}")
        return json.loads(resp.read().decode("utf-8"))


def _http_post_json(url: str, token: str, payload: dict, timeout_s: float) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-AIX-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        if response.status not in (200, 202):
            raise OSError(f"device returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def create_app(
    engine: InferenceEngine | None,
    analyzer=None,
    *,
    token: str = "",
    analyzer_loader=None,
    callback_client: RiskCallbackClient | None = None,
    pneumatic_proxy: PneumaticProxy | None = None,
    road_hazard_sender: RoadHazardSender | None = None,
    device_transport: Callable[[str, str, dict, float], dict] | None = None,
    semantic_client: SemanticGatewayClient | None = None,
    semantic_error: str = "",
    start_worker: bool = True,
) -> FastAPI:
    store = road_hazard_sender.store if road_hazard_sender is not None else LatestFrameStore()
    states = road_hazard_sender.states if road_hazard_sender is not None else ChainStateRepository("ready" if analyzer is not None else "loading")
    callback = callback_client or RiskCallbackClient(token=token)
    device_call = device_transport or _http_post_json
    pneumatic = pneumatic_proxy or PneumaticProxy(store, token=token)
    hazards = road_hazard_sender or RoadHazardSender(store, states, token=token)
    mode = OperatingModeController()
    worker = AnalysisWorker(store, states, callback, analyzer=analyzer, dispatch_enabled=mode.is_real)
    semantic_cache = SemanticResultCache(capacity=20)

    def send_semantic_indicator(frame: FrameEnvelope, payload: dict) -> dict:
        response = device_call(
            f"http://{frame.source_ip}:8080/semantic-indicator",
            token,
            payload,
            1.5,
        )
        if not isinstance(response, dict) or response.get("accepted") is not True:
            raise OSError("ESP32 rejected semantic indicator")
        return response

    semantic_worker = (
        SemanticAnalysisWorker(
            client=semantic_client,
            cache=semantic_cache,
            record=states.record_semantic,
            indicator=send_semantic_indicator,
        )
        if semantic_client is not None
        else None
    )
    states.set_semantic_enabled(
        semantic_worker is not None,
        error=semantic_error if semantic_worker is None else "",
    )
    if analyzer is not None:
        states.set_model(
            "ready",
            model=getattr(analyzer, "depth_model_name", "DA3-SMALL"),
            detector=getattr(analyzer, "detector_model_name", ""),
            backend=getattr(analyzer, "backend", "cuda"),
            gpu=getattr(engine, "device", "cuda"),
        )

    def load_models() -> None:
        try:
            loaded_analyzer = analyzer_loader()
            warmup = getattr(loaded_analyzer, "warmup", None)
            if callable(warmup):
                warmup()
            worker.set_analyzer(loaded_analyzer)
        except Exception as exc:
            states.set_model("error", error=str(exc))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if start_worker:
            worker.start()
            if semantic_worker is not None:
                semantic_worker.start()
        hazards.start()
        if analyzer is None and analyzer_loader is not None:
            threading.Thread(target=load_models, name="aix-model-loader", daemon=True).start()
        try:
            yield
        finally:
            worker.stop()
            if semantic_worker is not None:
                semantic_worker.stop()
            hazards.stop()

    app = FastAPI(title="AIX Depth Anything 3 Service", lifespan=lifespan)
    app.state.frame_store = store
    app.state.chain_states = states
    app.state.analysis_worker = worker
    app.state.pneumatic_proxy = pneumatic
    app.state.road_hazard_sender = hazards
    app.state.operating_mode = mode
    app.state.semantic_worker = semantic_worker
    app.state.semantic_cache = semantic_cache

    @app.get("/healthz")
    def healthz() -> dict[str, str | bool]:
        model_health = states.health()
        model = getattr(engine, "model_name", model_health["model"])
        device = getattr(engine, "device", model_health["gpu"])
        return {
            "ready": True,
            "http_ready": True,
            "model_ready": model_health["model_state"] == "ready",
            "model_state": model_health["model_state"],
            "model_error": model_health["model_error"],
            "model": model,
            "detector": model_health.get("detector", ""),
            "backend": model_health.get("backend", device),
            "device": device,
            "gpu": device,
            "operating_mode": mode.snapshot()["mode"],
            "semantic_enabled": semantic_worker is not None,
            "semantic_error": semantic_error if semantic_worker is None else "",
        }

    @app.post("/v1/frames", status_code=202)
    async def upload_frame(
        request: Request,
        x_aix_token: str | None = Header(default=None),
        x_device_id: str = Header(),
        x_boot_id: str = Header(),
        x_frame_seq: str = Header(),
        x_capture_ts_ms: str = Header(),
    ) -> dict:
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", x_device_id):
            raise HTTPException(status_code=422, detail="invalid device id")
        if not re.fullmatch(r"[0-9a-fA-F]{16}", x_boot_id):
            raise HTTPException(status_code=422, detail="boot id must be 16 hexadecimal characters")
        try:
            frame_seq = int(x_frame_seq)
            capture_ts_ms = int(x_capture_ts_ms)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="frame headers must be integers") from exc
        if frame_seq < 0 or capture_ts_ms < 0:
            raise HTTPException(status_code=422, detail="frame headers must be non-negative")
        image_bytes = await request.body()
        if len(image_bytes) > 256 * 1024:
            raise HTTPException(status_code=413, detail="JPEG exceeds 256 KiB")
        if not _is_jpeg(image_bytes):
            raise HTTPException(status_code=415, detail="request body must be a JPEG")
        received_ts_ms = int(time.time() * 1000)
        item = FrameEnvelope(
            device_id=x_device_id,
            boot_id=x_boot_id.lower(),
            frame_seq=frame_seq,
            capture_ts_ms=capture_ts_ms,
            source_ip=request.client.host if request.client else "127.0.0.1",
            jpeg=image_bytes,
            received_ts_ms=received_ts_ms,
        )
        queue_replaced = store.put(item)
        states.record_frame(item, queue_replaced)
        if semantic_worker is not None and mode.is_real():
            semantic_worker.offer(item)
        return {
            "type": "frame_ack",
            "version": 1,
            "device_id": item.device_id,
            "boot_id": item.boot_id,
            "frame_seq": item.frame_seq,
            "accepted": True,
            "queue_replaced": queue_replaced,
            "model_state": states.health()["model_state"],
            "server_ts_ms": received_ts_ms,
        }

    @app.get("/v1/frame/latest.jpg")
    def latest_frame(device_id: str) -> Response:
        item = store.latest(device_id)
        if item is None:
            raise HTTPException(status_code=404, detail="no frame for device")
        return Response(
            content=item.jpeg,
            media_type="image/jpeg",
            headers={
                "X-Device-Id": item.device_id,
                "X-Boot-Id": item.boot_id,
                "X-Frame-Seq": str(item.frame_seq),
                "X-Capture-Ts-Ms": str(item.capture_ts_ms),
                "X-Received-Ts-Ms": str(item.received_ts_ms),
            },
        )

    @app.get("/v1/frame/processed.jpg")
    def processed_frame(device_id: str) -> Response:
        item = store.latest_processed(device_id)
        if item is None:
            raise HTTPException(status_code=404, detail="no processed frame for device")
        return Response(
            content=item.jpeg,
            media_type="image/jpeg",
            headers={
                "X-Device-Id": item.device_id,
                "X-Boot-Id": item.boot_id,
                "X-Frame-Seq": str(item.frame_seq),
                "X-Capture-Ts-Ms": str(item.capture_ts_ms),
                "X-Received-Ts-Ms": str(item.received_ts_ms),
            },
        )

    @app.get("/v1/state/latest")
    def latest_state(device_id: str) -> dict:
        state = states.latest(device_id)
        if state is None:
            raise HTTPException(status_code=404, detail="no state for device")
        return state

    @app.get("/v1/semantic/{analysis_id}/keyframes/{index}.jpg")
    def semantic_keyframe(analysis_id: str, index: int) -> Response:
        if index not in (1, 2, 3):
            raise HTTPException(status_code=422, detail="keyframe index must be 1, 2, or 3")
        try:
            image_bytes = semantic_cache.keyframe(analysis_id, index)
        except KeyError:
            raise HTTPException(status_code=404, detail="semantic keyframe not found") from None
        return Response(content=image_bytes, media_type="image/jpeg")

    @app.post("/v1/collision-indicator/ack")
    async def collision_indicator_ack(
        request: Request,
        x_aix_token: str | None = Header(default=None),
    ) -> dict:
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        body = await request.body()
        if len(body) > 1024:
            raise HTTPException(status_code=413, detail="collision ACK payload too large")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="invalid collision ACK JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="collision ACK must be an object")
        device_id = payload.get("device_id")
        boot_id = payload.get("boot_id")
        impact_count = payload.get("impact_count")
        if (
            not isinstance(device_id, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", device_id)
            or not isinstance(boot_id, str)
            or not re.fullmatch(r"[0-9a-fA-F]{16}", boot_id)
            or isinstance(impact_count, bool)
            or not isinstance(impact_count, int)
            or impact_count < 0
        ):
            raise HTTPException(status_code=422, detail="invalid collision ACK identity")
        frame = _latest_device_frame(device_id)
        if frame.boot_id != boot_id.lower():
            raise HTTPException(status_code=409, detail="stale collision boot identity")
        return _device_call(
            frame,
            "/collision-indicator/ack",
            {
                "type": "collision_indicator_ack",
                "version": 1,
                "device_id": device_id,
                "boot_id": boot_id.lower(),
                "impact_count": impact_count,
            },
        )

    @app.get("/v1/operating-mode")
    def operating_mode() -> dict:
        snapshot = mode.snapshot()
        states.set_operating_mode(snapshot)
        return snapshot

    def _latest_device_frame(device_id: str) -> FrameEnvelope:
        frame = store.latest(device_id)
        if frame is None:
            raise HTTPException(status_code=503, detail="no recent frame for device; cannot route to ESP32")
        return frame

    def _device_call(frame: FrameEnvelope, endpoint: str, payload: dict) -> dict:
        try:
            response = device_call(f"http://{frame.source_ip}:8080{endpoint}", token, payload, 1.5)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"ESP32 endpoint unreachable at {frame.source_ip}:8080{endpoint}: {exc}") from exc
        if not isinstance(response, dict) or response.get("accepted") is not True:
            raise HTTPException(status_code=502, detail=f"ESP32 rejected {endpoint} request")
        return response

    @app.post("/v1/demo/session/start", status_code=202)
    async def demo_session_start(request: Request, x_aix_token: str | None = Header(default=None)) -> dict:
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail="demo session must be JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="demo session must be a JSON object")
        device_id_val = str(payload.get("device_id", ""))
        session_id = str(payload.get("session_id", ""))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", device_id_val) or not session_id:
            raise HTTPException(status_code=422, detail="invalid device_id or session_id")
        try:
            lease_ms = int(payload.get("lease_ms", 15_000))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="lease_ms must be an integer") from exc
        frame = _latest_device_frame(device_id_val)
        device_payload = {
            "type": "demo_session_start", "version": 1, "device_id": device_id_val,
            "boot_id": frame.boot_id, "session_id": session_id, "lease_ms": lease_ms,
        }
        _device_call(frame, "/demo/session/start", device_payload)
        started = mode.start(session_id, lease_ms=lease_ms)
        if not started["accepted"]:
            raise HTTPException(status_code=409, detail=started["error"])
        states.set_operating_mode(started)
        return started

    @app.post("/v1/demo/session/heartbeat", status_code=202)
    async def demo_session_heartbeat(request: Request, x_aix_token: str | None = Header(default=None)) -> dict:
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="demo heartbeat must be a JSON object")
        device_id_val = str(payload.get("device_id", ""))
        session_id = str(payload.get("session_id", ""))
        lease_ms = int(payload.get("lease_ms", 15_000))
        frame = _latest_device_frame(device_id_val)
        _device_call(frame, "/demo/session/heartbeat", {
            "type": "demo_session_heartbeat", "version": 1, "device_id": device_id_val,
            "boot_id": frame.boot_id, "session_id": session_id, "lease_ms": lease_ms,
        })
        result = mode.heartbeat(session_id, lease_ms=lease_ms)
        if not result["accepted"]:
            raise HTTPException(status_code=409, detail=result["error"])
        states.set_operating_mode(result)
        return result

    @app.post("/v1/demo/action", status_code=202)
    async def demo_action(request: Request, x_aix_token: str | None = Header(default=None)) -> dict:
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="demo action must be a JSON object")
        scene_id = payload.get("scene_id")
        if scene_id not in (4, 5, 6):
            raise HTTPException(status_code=422, detail="scene_id must be 4, 5, or 6")
        snapshot = mode.snapshot()
        states.set_operating_mode(snapshot)
        if snapshot["mode"] != OperatingModeController.DEMO:
            raise HTTPException(status_code=409, detail="demo mode is not active")
        device_id_val = str(payload.get("device_id", ""))
        session_id = str(payload.get("session_id", ""))
        if session_id != snapshot["session_id"]:
            raise HTTPException(status_code=409, detail="demo session is not active")
        frame = _latest_device_frame(device_id_val)
        now_ms = int(time.time() * 1000)
        result = _device_call(frame, "/demo/action", {
            "type": "demo_action", "version": 1, "device_id": device_id_val,
            "boot_id": frame.boot_id, "frame_seq": frame.frame_seq, "capture_ts_ms": now_ms,
            "session_id": session_id, "scene_id": scene_id,
        })
        return {"accepted": True, "scene_id": scene_id, "device_id": device_id_val,
                "frame_seq": frame.frame_seq, "ack": result}

    @app.post("/v1/demo/action/reset", status_code=202)
    async def demo_action_reset(request: Request, x_aix_token: str | None = Header(default=None)) -> dict:
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="demo reset must be a JSON object")
        snapshot = mode.snapshot()
        states.set_operating_mode(snapshot)
        if snapshot["mode"] != OperatingModeController.DEMO:
            raise HTTPException(status_code=409, detail="demo mode is not active")
        device_id_val = str(payload.get("device_id", ""))
        session_id = str(payload.get("session_id", ""))
        if session_id != snapshot["session_id"]:
            raise HTTPException(status_code=409, detail="demo session is not active")
        frame = _latest_device_frame(device_id_val)
        result = _device_call(frame, "/demo/action/reset", {
            "type": "demo_action_reset", "version": 1, "device_id": device_id_val,
            "boot_id": frame.boot_id, "session_id": session_id,
        })
        if not isinstance(result, dict) or result.get("accepted") is not True:
            raise HTTPException(status_code=502, detail="ESP32 rejected demo reset")
        return {"accepted": True, "device_id": device_id_val, "ack": result}

    @app.post("/v1/demo/session/end", status_code=202)
    async def demo_session_end(request: Request, x_aix_token: str | None = Header(default=None)) -> dict:
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="demo session must be a JSON object")
        device_id_val = str(payload.get("device_id", ""))
        session_id = str(payload.get("session_id", ""))
        frame = _latest_device_frame(device_id_val)
        _device_call(frame, "/demo/session/end", {
            "type": "demo_session_end", "version": 1, "device_id": device_id_val,
            "boot_id": frame.boot_id, "session_id": session_id,
        })
        result = mode.end(session_id)
        if not result["accepted"]:
            raise HTTPException(status_code=409, detail=result["error"])
        states.set_operating_mode(result)
        return result

    @app.post("/v1/road-hazards", status_code=202)
    async def road_hazards(request: Request, x_aix_token: str | None = Header(default=None)) -> dict:
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        try:
            payload = await request.json()
            event = RoadHazardEvent.from_payload(payload)
            created = hazards.accept(event)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail="road hazard must be JSON") from exc
        except RoadHazardValidationError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RoadHazardConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except RoadHazardUnavailableError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return {"accepted": True, "idempotent": not created, **event.snapshot()}

    @app.post("/v1/scenario-risk", status_code=202)
    async def scenario_risk(request: Request, x_aix_token: str | None = Header(default=None)) -> dict:
        """Accept demo scenario input and dispatch as real vision_risk to ESP32 /risk."""
        if not token or x_aix_token != token:
            raise HTTPException(status_code=401, detail="invalid link token")
        if not mode.is_real():
            states.set_operating_mode(mode.snapshot())
            raise HTTPException(status_code=409, detail="real dispatch paused while demo mode is active")
        try:
            payload = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail="scenario risk must be JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="scenario risk must be a JSON object")

        scene_id = payload.get("scene_id")
        if scene_id not in (4, 5, 6):
            raise HTTPException(status_code=422, detail="scene_id must be 4, 5, or 6")
        device_id_val = str(payload.get("device_id", ""))
        if not device_id_val or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", device_id_val):
            raise HTTPException(status_code=422, detail="invalid device_id")

        frame = store.latest(device_id_val)
        if frame is None:
            raise HTTPException(status_code=503, detail="no recent frame for device; cannot route to ESP32")

        # --- pre-dispatch health check ---
        # A caller-supplied transport is an explicit in-process test/dry-run
        # boundary; the production transport always probes the real receiver.
        source_ip = frame.source_ip
        if callback_client is None:
            healthz_url = f"http://{source_ip}:8080/healthz"
            try:
                health = _http_get(healthz_url, 2.0)
            except OSError as exc:
                raise HTTPException(status_code=503, detail=f"ESP32 health endpoint unreachable at {source_ip}:8080: {exc}")
            except json.JSONDecodeError:
                raise HTTPException(status_code=502, detail="ESP32 health check returned invalid JSON")

            if not isinstance(health, dict):
                raise HTTPException(status_code=502, detail="ESP32 health check response malformed")

            actual_device = str(health.get("device_id", ""))
            if actual_device != device_id_val:
                raise HTTPException(status_code=502,
                    detail=f"ESP32 identity mismatch at {source_ip}:8080: expected device={device_id_val}, got device={actual_device}")

            if not health.get("risk_receiver_ready"):
                raise HTTPException(status_code=502, detail=f"ESP32 risk_receiver not ready at {source_ip}:8080")
        # --- health check passed ---

        now_ms = int(time.time() * 1000)
        # A scene reuses the most recent real frame identity.  Firmware keeps
        # demo requests out of the real frame-sequence watermark, so it cannot
        # make subsequent camera risks appear out of order.
        scene_seq = frame.frame_seq
        boot_id = frame.boot_id
        command_id_str = f"{boot_id}:scene{scene_id}:{now_ms}"
        risk_payload = {
            "type": "vision_risk", "version": 1,
            "device_id": device_id_val, "boot_id": boot_id,
            "frame_seq": scene_seq, "capture_ts_ms": now_ms,
            "models": {"depth": "DA3-SMALL", "detector": "YOLO26m-COCO"},
            "depth_kind": "relative", "depth_p10": 0.05, "depth_median": 0.15,
            "confidence_median": 0.95, "detections": [],
            "risk_score": 85, "risk_band": "critical",
            "dominant_class": f"scenario_{scene_id:03d}",
            "reason": "scenario_demo", "latency_ms": 0, "valid": True,
            "actuation_hazard_active": True,
            "scene": scene_id,
            "voice_prompt": {"command_id": command_id_str, "track": scene_id},
        }

        try:
            ack = callback._transport(
                f"http://{frame.source_ip}:8080/risk", token, risk_payload, 0.5)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"ESP32 /risk call failed at {frame.source_ip}:8080: {exc}") from exc

        if not isinstance(ack, dict) or ack.get("type") != "action_ack" or ack.get("accepted") is not True:
            raise HTTPException(status_code=502, detail=f"ESP32 rejected scenario risk at {frame.source_ip}:8080")
        return {"accepted": True, "scene_id": scene_id, "device_id": device_id_val,
                "frame_seq": scene_seq, "ack": ack}

    @app.post("/v1/pneumatic/command")
    async def pneumatic_command(device_id: str, request: Request) -> dict:
        try:
            payload = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=422, detail="pneumatic command must be JSON") from exc
        if not isinstance(payload, dict):
            raise HTTPException(status_code=422, detail="pneumatic command must be a JSON object")
        try:
            return pneumatic.command(device_id, payload)
        except StaleDeviceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PneumaticProtocolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PneumaticProxyError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.get("/v1/pneumatic/config")
    def pneumatic_config(device_id: str) -> dict:
        try:
            return pneumatic.config(device_id)
        except StaleDeviceError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PneumaticProtocolError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PneumaticProxyError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

    @app.post("/v1/infer")
    async def infer(
        request: Request,
        x_frame_seq: str = Header(),
        x_capture_ts_ms: str = Header(),
    ) -> dict[str, int | float | str | bool]:
        if engine is None:
            raise HTTPException(status_code=503, detail="inference unavailable")
        try:
            frame_seq = int(x_frame_seq)
            capture_ts_ms = int(x_capture_ts_ms)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="frame headers must be integers") from exc

        image_bytes = await request.body()
        if not _is_jpeg(image_bytes):
            raise HTTPException(status_code=415, detail="request body must be a JPEG")

        started = perf_counter()
        try:
            summary = engine.infer_jpeg(image_bytes)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="inference unavailable") from exc

        return build_vision_depth_response(
            frame_seq=frame_seq,
            capture_ts_ms=capture_ts_ms,
            depth_p10=summary.depth_p10,
            depth_median=summary.depth_median,
            confidence_median=summary.confidence_median,
            latency_ms=(perf_counter() - started) * 1000.0,
        )

    @app.post("/v1/analyze")
    async def analyze(
        request: Request,
        x_frame_seq: str = Header(),
        x_capture_ts_ms: str = Header(),
        x_session_id: str = Header(),
    ) -> dict:
        if analyzer is None:
            raise HTTPException(status_code=503, detail="analysis unavailable")
        try:
            frame_seq = int(x_frame_seq)
            capture_ts_ms = int(x_capture_ts_ms)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="frame headers must be integers") from exc
        image_bytes = await request.body()
        if not _is_jpeg(image_bytes):
            raise HTTPException(status_code=415, detail="request body must be a JPEG")
        try:
            return analyzer.analyze_jpeg(
                image_bytes,
                frame_seq=frame_seq,
                capture_ts_ms=capture_ts_ms,
                session_id=x_session_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=503, detail="analysis unavailable") from exc

    return app
