from __future__ import annotations

from time import perf_counter
from typing import Protocol

from fastapi import FastAPI, Header, HTTPException, Request

from inference import PredictionSummary
from schemas import build_vision_depth_response


class InferenceEngine(Protocol):
    model_name: str
    device: str

    def infer_jpeg(self, image_bytes: bytes) -> PredictionSummary: ...


def _is_jpeg(image_bytes: bytes) -> bool:
    return len(image_bytes) >= 4 and image_bytes[:2] == b"\xff\xd8" and image_bytes[-2:] == b"\xff\xd9"


def create_app(engine: InferenceEngine | None, analyzer=None) -> FastAPI:
    app = FastAPI(title="AIX Depth Anything 3 Service")

    @app.get("/healthz")
    def healthz() -> dict[str, str | bool]:
        model = getattr(engine, "model_name", getattr(analyzer, "depth_model_name", "unknown"))
        device = getattr(engine, "device", "cuda")
        return {"ready": True, "model": model, "device": device}

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
