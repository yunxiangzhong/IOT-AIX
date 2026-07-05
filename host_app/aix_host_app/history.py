from __future__ import annotations

from collections import deque

from .models import PressureSample


class PressureHistory:
    def __init__(self, max_points: int = 240) -> None:
        if max_points <= 0:
            raise ValueError("max_points must be positive")
        self._samples: deque[PressureSample] = deque(maxlen=max_points)

    def add(self, sample: PressureSample) -> None:
        self._samples.append(sample)

    def latest(self) -> PressureSample | None:
        if not self._samples:
            return None
        return self._samples[-1]

    def clear(self) -> None:
        self._samples.clear()

    def seq_values(self) -> list[int]:
        return [sample.seq for sample in self._samples]

    def kpa_values(self) -> list[float]:
        return [sample.kpa for sample in self._samples]

    def filtered_values(self) -> list[float]:
        return [sample.filtered_kpa for sample in self._samples]

    def mv_values(self) -> list[int]:
        return [sample.mv for sample in self._samples]
