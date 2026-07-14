from __future__ import annotations

import re
import threading
import time
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

from frame_pipeline import AnalysisWorker, ChainStateRepository, FrameEnvelope, LatestFrameStore, RiskCallbackClient
from inference import PredictionSummary
from schemas import build_vision_depth_response


class InferenceEngine(Protocol):
    model_name: str
    device: str

    def infer_jpeg(self, image_bytes: bytes) -> PredictionSummary: ...


def _is_jpeg(image_bytes: bytes) -> bool:
    return len(image_bytes) >= 4 and image_bytes[:2] == b"\xff\xd8" and image_bytes[-2:] == b"\xff\xd9"


def create_app(
    engine: InferenceEngine | None,
    analyzer=None,
    *,
    token: str = "",
    analyzer_loader=None,
    callback_client: RiskCallbackClient | None = None,
    start_worker: bool = True,
) -> FastAPI:
    store = LatestFrameStore()
    states = ChainStateRepository("ready" if analyzer is not None else "loading")
    callback = callback_client or RiskCallbackClient(token=token)
    worker = AnalysisWorker(store, states, callback, analyzer=analyzer)
    if analyzer is not None:
        states.set_model(
            "ready",
            model=getattr(analyzer, "depth_model_name", "DA3-SMALL"),
            gpu=getattr(engine, "device", "cuda"),
        )

    def load_models() -> None:
        try:
            worker.set_analyzer(analyzer_loader())
        except Exception as exc:
            states.set_model("error", error=str(exc))

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if start_worker:
            worker.start()
        if analyzer is None and analyzer_loader is not None:
            threading.Thread(target=load_models, name="aix-model-loader", daemon=True).start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="AIX Depth Anything 3 Service", lifespan=lifespan)
    app.state.frame_store = store
    app.state.chain_states = states
    app.state.analysis_worker = worker

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
            "device": device,
            "gpu": device,
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

    @app.get("/v1/state/latest")
    def latest_state(device_id: str) -> dict:
        state = states.latest(device_id)
        if state is None:
            raise HTTPException(status_code=404, detail="no state for device")
        return state

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
