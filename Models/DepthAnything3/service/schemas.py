from __future__ import annotations

import math


def build_vision_depth_response(
    *,
    frame_seq: int,
    capture_ts_ms: int,
    depth_p10: float,
    depth_median: float,
    confidence_median: float,
    latency_ms: float,
) -> dict[str, int | float | str | bool]:
    measurements = (depth_p10, depth_median, confidence_median, latency_ms)
    if frame_seq < 0 or capture_ts_ms < 0 or not all(math.isfinite(value) for value in measurements):
        raise ValueError("vision_depth fields must be finite non-negative values")

    return {
        "type": "vision_depth",
        "version": 1,
        "frame_seq": frame_seq,
        "capture_ts_ms": capture_ts_ms,
        "model": "DA3-SMALL",
        "depth_kind": "relative",
        "depth_p10": depth_p10,
        "depth_median": depth_median,
        "confidence_median": confidence_median,
        "latency_ms": latency_ms,
        "valid": True,
    }


def build_vision_risk_response(
    *,
    frame_seq: int,
    capture_ts_ms: int,
    depth_p10: float,
    depth_median: float,
    confidence_median: float,
    detections: list[dict],
    risk_score: int,
    risk_band: str,
    dominant_class: str,
    reason: str,
    latency_ms: float,
    detector_model: str = "YOLO26m-COCO",
    actuation_hazard_active: bool | None = None,
) -> dict:
    measurements = (depth_p10, depth_median, confidence_median, latency_ms)
    if frame_seq < 0 or capture_ts_ms < 0 or not all(math.isfinite(value) for value in measurements):
        raise ValueError("vision_risk fields must be finite non-negative values")
    if not 0 <= risk_score <= 100 or risk_band not in {"low", "attention", "high", "critical"}:
        raise ValueError("risk_score or risk_band is invalid")
    payload: dict = {
        "type": "vision_risk",
        "version": 1,
        "frame_seq": frame_seq,
        "capture_ts_ms": capture_ts_ms,
        "models": {"depth": "DA3-SMALL", "detector": detector_model},
        "depth_kind": "relative",
        "depth_p10": depth_p10,
        "depth_median": depth_median,
        "confidence_median": confidence_median,
        "detections": detections,
        "risk_score": risk_score,
        "risk_band": risk_band,
        "dominant_class": dominant_class,
        "reason": reason,
        "latency_ms": latency_ms,
        "valid": True,
    }
    if actuation_hazard_active is not None:
        payload["actuation_hazard_active"] = actuation_hazard_active
    return payload
