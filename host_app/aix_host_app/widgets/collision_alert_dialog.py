from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..collision_state import ProtectionReadiness
from ..models import MotionEvent, PneumaticStatusEvent


class CollisionAlertDialog(QtWidgets.QDialog):
    """Persistent host-only notice for a newly observed collision."""

    acknowledged = QtCore.Signal()

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(
            parent,
            QtCore.Qt.WindowType.Tool | QtCore.Qt.WindowType.WindowStaysOnTopHint,
        )
        self._allow_close = False
        self.setModal(False)
        self.setWindowTitle("碰撞告警")
        self.setMinimumWidth(440)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        self.title_label = QtWidgets.QLabel("检测到碰撞，请确认人员与设备状态")
        self.title_label.setStyleSheet(
            "background: #b91c1c; color: white; font-size: 18px; "
            "font-weight: 700; padding: 12px; border-radius: 6px;"
        )
        self.title_label.setWordWrap(True)
        layout.addWidget(self.title_label)

        self.count_label = QtWidgets.QLabel()
        self.detail_label = QtWidgets.QLabel()
        self.readiness_label = QtWidgets.QLabel()
        self.pneumatic_label = QtWidgets.QLabel("气动实际状态：等待设备状态上报")
        self.airbag_label = QtWidgets.QLabel(
            "RGB 模拟 Airbag 已打开（白色常亮，不代表真实充气）"
        )
        self.ack_status_label = QtWidgets.QLabel()
        for label in (
            self.count_label,
            self.detail_label,
            self.airbag_label,
            self.readiness_label,
            self.pneumatic_label,
            self.ack_status_label,
        ):
            label.setWordWrap(True)
            layout.addWidget(label)

        self.ack_button = QtWidgets.QPushButton("确认已知晓")
        self.ack_button.setStyleSheet(
            "QPushButton { background: #991b1b; color: white; font-weight: 700; "
            "padding: 10px 18px; border-radius: 5px; }"
            "QPushButton:hover { background: #7f1d1d; }"
        )
        self.ack_button.clicked.connect(self.acknowledge)
        layout.addWidget(self.ack_button, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

    def show_collision(
        self,
        event: MotionEvent,
        total_count: int,
        readiness: ProtectionReadiness | None,
    ) -> None:
        self.count_label.setText(f"本会话待确认碰撞次数：{total_count}")
        self.detail_label.setText(
            "碰撞详情："
            f"设备时间 {event.ts_ms} ms；加速度 {self._number(event.accel_norm_g)} g；"
            f"增量 {self._number(event.accel_delta_g)} g；采样间隔 {self._interval(event.sample_interval_ms)}；"
            f"倾角 {self._number(event.tilt_deg)}°"
        )
        self._apply_readiness(readiness)
        self.ack_status_label.clear()
        self.ack_button.setText("确认已知晓")
        self.ack_button.setEnabled(True)
        self.show()
        self.raise_()
        self.activateWindow()

    def apply_pneumatic_status(
        self,
        event: PneumaticStatusEvent,
        readiness: ProtectionReadiness | None,
    ) -> None:
        self.pneumatic_label.setText(
            "气动实际状态："
            f"状态 {event.state}；触发 {event.trigger or '无'}；故障 {event.fault or '无'}；"
            f"压力 {event.pressure_kpa:.2f} kPa；泵 {'开' if event.pump_on else '关'}；"
            f"阀 {'开' if event.valve_on else '关'}"
        )
        self._apply_readiness(readiness)

    def acknowledge(self) -> None:
        self.ack_button.setEnabled(False)
        self.ack_button.setText("正在等待 ESP32 确认…")
        self.ack_status_label.setText("正在清除匹配的 RGB 模拟 Airbag 白灯")
        self.acknowledged.emit()

    def acknowledge_succeeded(self) -> None:
        self.ack_status_label.setText("ESP32 已确认，白色模拟 Airbag 指示已清除")
        self._allow_close = True
        self.close()
        self._allow_close = False

    def acknowledge_failed(self, message: str) -> None:
        self.ack_status_label.setText(f"确认失败：{message}；请重试")
        self.ack_button.setText("重试确认")
        self.ack_button.setEnabled(True)

    def shutdown(self) -> None:
        self._allow_close = True
        self.close()

    def closeEvent(self, event) -> None:
        if not self._allow_close:
            event.ignore()
            return
        super().closeEvent(event)

    def _apply_readiness(self, readiness: ProtectionReadiness | None) -> None:
        if readiness is None:
            self.readiness_label.setText("气动保护状态：等待设备状态上报")
            return
        state = "允许" if readiness.allowed else "阻塞"
        self.readiness_label.setText(f"气动保护状态：{state}；{readiness.reason}")

    @staticmethod
    def _number(value: float | None) -> str:
        return "—" if value is None else f"{value:.2f}"

    @staticmethod
    def _interval(value: int | None) -> str:
        return "—" if value is None else f"{value} ms"
