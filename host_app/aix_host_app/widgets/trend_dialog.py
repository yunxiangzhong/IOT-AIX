from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets


@dataclass(frozen=True)
class TrendSample:
    timestamp_ms: int
    value: float
    label: str = ""


class TrendStore:
    WINDOW_MS = 60_000

    def __init__(self) -> None:
        self._samples: dict[str, deque[TrendSample]] = defaultdict(deque)

    def add(self, metric_key: str, timestamp_ms: int, value: float, label: str = "") -> None:
        samples = self._samples[metric_key]
        sample = TrendSample(int(timestamp_ms), float(value), str(label))
        if samples and sample.timestamp_ms < samples[-1].timestamp_ms:
            return
        if samples and sample.timestamp_ms == samples[-1].timestamp_ms:
            samples[-1] = sample
        else:
            samples.append(sample)
        self._trim(metric_key, sample.timestamp_ms)

    def samples(self, metric_key: str, window_ms: int = WINDOW_MS) -> list[TrendSample]:
        samples = self._samples.get(metric_key)
        if not samples:
            return []
        self._trim(metric_key, samples[-1].timestamp_ms)
        cutoff = samples[-1].timestamp_ms - int(window_ms)
        return [sample for sample in samples if sample.timestamp_ms >= cutoff]

    def stats(self, metric_key: str, window_ms: int = WINDOW_MS) -> tuple[float, float, float] | None:
        values = [sample.value for sample in self.samples(metric_key, window_ms)]
        if not values:
            return None
        return values[-1], min(values), max(values)

    def _trim(self, metric_key: str, newest_ms: int) -> None:
        samples = self._samples[metric_key]
        cutoff = int(newest_ms) - self.WINDOW_MS
        while samples and samples[0].timestamp_ms < cutoff:
            samples.popleft()


class TrendDialog(QtWidgets.QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, QtCore.Qt.WindowType.Tool)
        self.setObjectName("trendDialog")
        self.setModal(False)
        self.setMinimumSize(680, 420)
        self.resize(760, 480)
        self.setWindowTitle("趋势")
        self._metric_key = ""
        self._unit = ""
        self._store: TrendStore | None = None
        self._paused = False

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)
        header = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel("趋势")
        self.title_label.setObjectName("trendDialogTitle")
        self.stats_label = QtWidgets.QLabel("等待趋势数据")
        self.stats_label.setObjectName("trendDialogStats")
        self.pause_button = QtWidgets.QPushButton("暂停")
        self.pause_button.setCheckable(True)
        self.pause_button.clicked.connect(self._toggle_pause)
        close_button = QtWidgets.QPushButton("关闭")
        close_button.clicked.connect(self.close)
        header.addWidget(self.title_label)
        header.addWidget(self.stats_label, 1)
        header.addWidget(self.pause_button)
        header.addWidget(close_button)
        root.addLayout(header)

        self.plot = pg.PlotWidget()
        self.plot.setBackground("#FAFAFC")
        self.plot.showGrid(x=True, y=True, alpha=0.18)
        self.plot.setLabel("bottom", "时间", units="s")
        self.plot.setLabel("left", "数值")
        self.plot.getPlotItem().hideButtons()
        root.addWidget(self.plot, 1)

    def set_metric(self, metric_key: str, title: str, unit: str, store: TrendStore) -> None:
        self._metric_key = metric_key
        self._unit = unit
        self._store = store
        self.title_label.setText(title)
        self.setWindowTitle(f"{title}趋势")
        self.refresh_plot()

    def set_paused(self, paused: bool) -> None:
        self._paused = bool(paused)
        self.pause_button.setChecked(self._paused)
        self.pause_button.setText("继续" if self._paused else "暂停")

    def refresh_plot(self) -> None:
        if self._paused or self._store is None or not self._metric_key:
            return
        self.plot.clear()
        keys = ("acceleration", "tilt") if self._metric_key == "motion" else (self._metric_key,)
        colors = ("#007AFF", "#A05A00")
        all_samples: list[TrendSample] = []
        for index, key in enumerate(keys):
            series = self._store.samples(key)
            all_samples.extend(series)
            if not series:
                continue
            x0 = series[-1].timestamp_ms
            x = [(sample.timestamp_ms - x0) / 1000.0 for sample in series]
            y = [sample.value for sample in series]
            name = "加速度" if key == "acceleration" else "倾角" if key == "tilt" else self.title_label.text()
            self.plot.plot(x, y, pen=pg.mkPen(colors[index % len(colors)], width=2), name=name)
        stats = self._store.stats(keys[0])
        if stats is None:
            self.stats_label.setText("正在收集趋势数据")
            return
        current, minimum, maximum = stats
        self.stats_label.setText(f"当前 {current:.2f} {self._unit} · 最小 {minimum:.2f} · 最大 {maximum:.2f}")
        if self._metric_key == "risk_score":
            self.plot.setYRange(0, 100, padding=0.02)

    def _toggle_pause(self, checked: bool) -> None:
        self.set_paused(checked)
        self.refresh_plot()
