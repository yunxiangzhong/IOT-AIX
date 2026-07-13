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
