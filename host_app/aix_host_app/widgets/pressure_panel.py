from __future__ import annotations

import pyqtgraph as pg
from PySide6 import QtCore, QtWidgets

from ..history import PressureHistory
from ..models import PressureSample
from ..plot_scaling import pressure_x_range, pressure_y_range


class PressurePanel(QtWidgets.QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.history = PressureHistory(max_points=240)

        self.value_label = QtWidgets.QLabel("--.- kPa")
        self.value_label.setObjectName("metricValue")
        self.status_label = QtWidgets.QLabel("等待气压样本")
        self.status_label.setObjectName("muted")
        self.detail_label = QtWidgets.QLabel("raw -- | -- mV | seq --")
        self.detail_label.setObjectName("muted")
        self.follow_button = QtWidgets.QToolButton()
        self.follow_button.setObjectName("followButton")
        self.follow_button.setCheckable(True)
        self.follow_button.setChecked(True)
        self.follow_button.setToolTip("开启后横轴跟随最新气压样本；关闭后可手动拖拽查看历史")
        self._set_auto_follow_label(True)

        self.plot = pg.PlotWidget(background="#f8fbf8")
        self.plot.setMenuEnabled(False)
        self.plot.showGrid(x=True, y=True, alpha=0.18)
        self.plot.setLabel("left", "Pressure", units="kPa")
        self.plot.setLabel("bottom", "Sample seq")
        self.plot.addLegend(offset=(12, 12))
        self.plot.setYRange(0, 10, padding=0)
        self.plot.setXRange(0, 60, padding=0)
        self.kpa_curve = self.plot.plot(
            [], [], pen=pg.mkPen("#8a6f2a", width=2), name="raw kPa"
        )
        self.filtered_curve = self.plot.plot(
            [], [], pen=pg.mkPen("#0f766e", width=3), name="filtered kPa"
        )

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QtWidgets.QHBoxLayout()
        left = QtWidgets.QVBoxLayout()
        title = QtWidgets.QLabel("气囊压力")
        title.setObjectName("sectionTitle")
        left.addWidget(title)
        left.addWidget(self.detail_label)
        header.addLayout(left)
        header.addWidget(self.follow_button, alignment=QtCore.Qt.AlignmentFlag.AlignTop)
        header.addStretch(1)

        metric = QtWidgets.QVBoxLayout()
        metric.addWidget(self.value_label, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        metric.addWidget(self.status_label, alignment=QtCore.Qt.AlignmentFlag.AlignRight)
        header.addLayout(metric)
        layout.addLayout(header)
        layout.addWidget(self.plot, stretch=1)

        self.follow_button.toggled.connect(self._set_auto_follow_enabled)

    def reset(self) -> None:
        self.history.clear()
        self.kpa_curve.setData([], [])
        self.filtered_curve.setData([], [])
        self.plot.setYRange(0, 10, padding=0)
        self.plot.setXRange(0, 60, padding=0)
        self.value_label.setText("--.- kPa")
        self.detail_label.setText("raw -- | -- mV | seq --")
        self._set_status("等待气压样本", "muted")

    def update_sample(self, sample: PressureSample) -> None:
        self.history.add(sample)
        self.kpa_curve.setData(self.history.seq_values(), self.history.kpa_values())
        self.filtered_curve.setData(self.history.seq_values(), self.history.filtered_values())
        low, high = pressure_y_range(
            self.history.kpa_values() + self.history.filtered_values()
        )
        self.plot.setYRange(low, high, padding=0)
        if self.follow_button.isChecked():
            self._apply_x_follow()

        self.value_label.setText(f"{sample.filtered_kpa:.1f} kPa")
        self.detail_label.setText(f"raw {sample.raw} | {sample.mv} mV | seq {sample.seq}")

        if sample.over_pressure:
            self._set_status("过压预警", "statusDanger")
        elif not sample.valid:
            self._set_status("传感器电压异常", "statusWarn")
        else:
            self._set_status("闭环反馈正常", "statusOk")

    def _apply_x_follow(self) -> None:
        low, high = pressure_x_range(self.history.seq_values())
        self.plot.setXRange(low, high, padding=0)

    def _set_auto_follow_enabled(self, enabled: bool) -> None:
        self._set_auto_follow_label(enabled)
        if enabled and self.history.latest() is not None:
            self._apply_x_follow()

    def _set_auto_follow_label(self, enabled: bool) -> None:
        self.follow_button.setText("自动跟随：开" if enabled else "自动跟随：关")

    def _set_status(self, text: str, object_name: str) -> None:
        self.status_label.setText(text)
        self.status_label.setObjectName(object_name)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
