from __future__ import annotations

from PySide6 import QtWidgets

from ..models import MotionEvent


class MotionPanel(QtWidgets.QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        title = QtWidgets.QLabel("运动模块")
        title.setObjectName("sectionTitle")
        self.accel_value = QtWidgets.QLabel("-- g")
        self.accel_value.setObjectName("metricSmallValue")
        self.tilt_value = QtWidgets.QLabel("-- °")
        self.tilt_value.setObjectName("metricSmallValue")
        self.status_label = QtWidgets.QLabel("MPU6050 模块未接入")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.addWidget(QtWidgets.QLabel("加速度模长"), 0, 0)
        grid.addWidget(self.accel_value, 1, 0)
        grid.addWidget(QtWidgets.QLabel("倾角"), 0, 1)
        grid.addWidget(self.tilt_value, 1, 1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addLayout(grid)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    def update_motion(self, event: MotionEvent) -> None:
        self.accel_value.setText(f"{event.accel_norm_g:.2f} g" if event.accel_norm_g is not None else "-- g")
        self.tilt_value.setText(f"{event.tilt_deg:.1f} °" if event.tilt_deg is not None else "-- °")
        if event.calibrated:
            events = "冲击" if event.impact else "快速倾斜" if event.rapid_tilt else "无危险事件"
            self.status_label.setText(f"MPU6050 seq {event.seq} · {events}")
            self.status_label.setObjectName("statusOk")
        else:
            self.status_label.setText("MPU6050 校准中或未接入")
            self.status_label.setObjectName("muted")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
