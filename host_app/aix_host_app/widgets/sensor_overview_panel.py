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
        self.accel = _MetricCell("加速度模长", "-- g", "模块未接入")
        self.tilt = _MetricCell("倾角", "-- °", "模块未接入")
        self.risk = _MetricCell("PC视觉风险", "--", "等待模型")
        self.airbag = _MetricCell("气囊目标", "0%", "等待动作")

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        cells = (self.pressure, self.accel, self.tilt, self.risk, self.airbag)
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
        if not sample.valid:
            self.pressure.set_metric("— kPa", "电压异常", "statusWarn")
            return
        if sample.over_pressure:
            status = "过压预警"
            object_name = "statusDanger"
        else:
            status = "反馈正常"
            object_name = "statusOk"
        self.pressure.set_metric(f"{sample.filtered_kpa:.1f} kPa", status, object_name)

    def update_motion(self, event: MotionEvent) -> None:
        accel = f"{event.accel_norm_g:.2f} g" if event.accel_norm_g is not None else "-- g"
        tilt = f"{event.tilt_deg:.1f} °" if event.tilt_deg is not None else "-- °"
        self.accel.set_metric(accel, "MPU6050 已校准" if event.calibrated else "MPU6050 未校准")
        self.tilt.set_metric(tilt, "危险事件锁存" if event.danger_latched else "运动诊断")

    def update_vision_risk(self, payload: dict) -> None:
        score = int(payload.get("risk_score", 0))
        band = {"low": "低", "attention": "注意", "high": "高", "critical": "严重"}.get(payload.get("risk_band"), "未知")
        object_name = "statusDanger" if score >= 80 else "statusWarn" if score >= 30 else "statusOk"
        self.risk.set_metric(str(score), f"{band} | {payload.get('dominant_class') or '无分类目标'}", object_name)
