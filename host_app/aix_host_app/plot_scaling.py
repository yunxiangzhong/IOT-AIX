from __future__ import annotations

from collections.abc import Iterable


def pressure_x_range(
    seq_values: Iterable[int],
    *,
    window_points: int = 180,
    min_span: int = 60,
    right_padding: int = 5,
) -> tuple[int, int]:
    readings = [int(value) for value in seq_values]
    if not readings:
        return 0, min_span

    latest = readings[-1]
    high = latest + right_padding
    span = max(min_span, window_points)
    low = max(0, high - span)
    if high - low < min_span:
        high = low + min_span
    return low, high


def pressure_y_range(
    values: Iterable[float],
    *,
    min_span: float = 8.0,
    padding_ratio: float = 0.25,
    lower_bound: float = 0.0,
    upper_bound: float = 200.0,
) -> tuple[float, float]:
    readings = [float(value) for value in values]
    if not readings:
        return lower_bound, lower_bound + min_span

    low = min(readings)
    high = max(readings)
    span = high - low
    padded_span = max(span * (1.0 + padding_ratio * 2.0), min_span)
    center = (low + high) / 2.0
    range_low = center - padded_span / 2.0
    range_high = center + padded_span / 2.0

    if range_low < lower_bound:
        range_high += lower_bound - range_low
        range_low = lower_bound

    if range_high > upper_bound:
        range_low -= range_high - upper_bound
        range_high = upper_bound
        range_low = max(lower_bound, range_low)

    if range_high - range_low < min_span:
        range_high = min(upper_bound, range_low + min_span)

    return range_low, range_high

