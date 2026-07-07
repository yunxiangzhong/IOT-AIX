from __future__ import annotations

from PySide6 import QtWidgets

from ..models import MotionEvent


class MotionPanel(QtWidgets.QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        title = QtWidgets.QLabel("运动模块")
        title.setObjectName("sectionTitle")
        self.speed_value = QtWidgets.QLabel("-- m/s")
        self.speed_value.setObjectName("metricSmallValue")
        self.accel_value = QtWidgets.QLabel("-- m/s²")
        self.accel_value.setObjectName("metricSmallValue")
        self.status_label = QtWidgets.QLabel("速度 / 加速度模块未接入")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)

        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)
        grid.addWidget(QtWidgets.QLabel("速度"), 0, 0)
        grid.addWidget(self.speed_value, 1, 0)
        grid.addWidget(QtWidgets.QLabel("加速度"), 0, 1)
        grid.addWidget(self.accel_value, 1, 1)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addLayout(grid)
        layout.addWidget(self.status_label)
        layout.addStretch(1)

    def update_motion(self, event: MotionEvent) -> None:
        self.speed_value.setText(f"{event.speed_mps:.2f} m/s" if event.speed_valid else "-- m/s")
        self.accel_value.setText(f"{event.accel_mps2:.2f} m/s²" if event.accel_valid else "-- m/s²")
        if event.speed_valid or event.accel_valid:
            self.status_label.setText(f"motion seq {event.seq}")
            self.status_label.setObjectName("statusOk")
        else:
            self.status_label.setText("速度 / 加速度模块未接入")
            self.status_label.setObjectName("muted")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
