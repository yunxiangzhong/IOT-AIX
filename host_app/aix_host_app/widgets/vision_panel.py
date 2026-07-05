from __future__ import annotations

from PySide6 import QtCore, QtWidgets


class VisionPanel(QtWidgets.QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("视觉感知")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.frame = QtWidgets.QLabel("Camera frame")
        self.frame.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.frame.setMinimumHeight(210)
        self.frame.setStyleSheet(
            "background:#e3ede8;border:1px dashed #8aa49b;border-radius:8px;"
            "color:#61736e;font-weight:700;"
        )
        layout.addWidget(self.frame)

        self.scene_label = QtWidgets.QLabel("场景：待接入")
        self.scene_label.setObjectName("muted")
        self.target_label = QtWidgets.QLabel("目标：待接入")
        self.target_label.setObjectName("muted")
        self.risk_label = QtWidgets.QLabel("风险等级 0")
        self.risk_label.setObjectName("statusOk")
        self.action_label = QtWidgets.QLabel("气囊策略：保持")
        self.action_label.setObjectName("muted")

        for widget in (self.scene_label, self.target_label, self.risk_label, self.action_label):
            layout.addWidget(widget)

        layout.addStretch(1)

    def set_placeholder_state(self) -> None:
        self.scene_label.setText("场景：待接入")
        self.target_label.setText("目标：待接入")
        self.risk_label.setText("风险等级 0")
        self.action_label.setText("气囊策略：保持")
