from __future__ import annotations

from PySide6 import QtWidgets

from ..models import MotionEvent, PressureSample


class _MetricCell(QtWidgets.QFrame):
    def __init__(self, title: str, value: str, status: str = "等待数据", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("metricCell")
        self.title = QtWidgets.QLabel(title)
        self.title.setObjectName("metricTitle")
        self.value = QtWidgets.QLabel(value)
        self.value.setObjectName("metricCellValue")
        self.status = QtWidgets.QLabel(status)
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.status)

    def set_metric(self, value: str, status: str, status_object: str = "muted") -> None:
        self.value.setText(value)
        self.status.setText(status)
        self.status.setObjectName(status_object)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)


class SensorOverviewPanel(QtWidgets.QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        self.pressure = _MetricCell("压力", "--.- kPa", "等待样本")
        self.speed = _MetricCell("速度", "-- m/s", "模块未接入")
        self.accel = _MetricCell("加速度", "-- m/s²", "模块未接入")
        self.risk = _MetricCell("ESP风险", "0", "等待 ESP")
        self.airbag = _MetricCell("气囊目标", "0%", "等待动作")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        cells = (self.pressure, self.speed, self.accel, self.risk, self.airbag)
        for idx, cell in enumerate(cells):
            layout.addWidget(cell, 1)
            if idx < len(cells) - 1:
                divider = QtWidgets.QFrame()
                divider.setFrameShape(QtWidgets.QFrame.Shape.VLine)
                divider.setFrameShadow(QtWidgets.QFrame.Shadow.Plain)
                divider.setStyleSheet("color: #ECECE8; background-color: #ECECE8;")
                divider.setFixedWidth(1)
                layout.addWidget(divider)

    def update_pressure(self, sample: PressureSample) -> None:
        if sample.over_pressure:
            status = "过压预警"
            object_name = "statusDanger"
        elif not sample.valid:
            status = "电压异常"
            object_name = "statusWarn"
        else:
            status = "反馈正常"
            object_name = "statusOk"
        self.pressure.set_metric(f"{sample.filtered_kpa:.1f} kPa", status, object_name)

    def update_motion(self, event: MotionEvent) -> None:
        speed = f"{event.speed_mps:.2f} m/s" if event.speed_valid else "-- m/s"
        accel = f"{event.accel_mps2:.2f} m/s²" if event.accel_valid else "-- m/s²"
        self.speed.set_metric(speed, "速度有效" if event.speed_valid else "速度未接入")
        self.accel.set_metric(accel, "加速度有效" if event.accel_valid else "加速度未接入")
