from __future__ import annotations

import math

from .models import PressureSample


def make_simulated_pressure_sample(seq: int, elapsed_ms: int) -> PressureSample:
    t = elapsed_ms / 1000.0
    breath = 96.0 + 24.0 * math.sin(t * 0.9)
    ripple = 6.0 * math.sin(t * 2.7 + 0.8)
    kpa = _clamp(breath + ripple, 0.0, 200.0)
    filtered = _clamp((breath * 0.82) + (kpa * 0.18), 0.0, 200.0)
    mv = int(200 + (filtered / 200.0) * 2500)
    raw = int((mv / 3300.0) * 4095)
    over_pressure = filtered >= 180.0
    valid = 100 <= mv <= 2900

    return PressureSample(
        seq=seq,
        ts_ms=elapsed_ms,
        raw=raw,
        mv=mv,
        kpa=kpa,
        filtered_kpa=filtered,
        over_pressure=over_pressure,
        valid=valid,
        source="simulated",
    )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))
