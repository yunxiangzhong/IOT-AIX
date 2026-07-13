from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..models import CameraStatusEvent


class VisionPanel(QtWidgets.QFrame):
    """OV5640 health display; image processing remains on the ESP32-S3."""

    CAMERA_STATUS_TIMEOUT_MS = 3000

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._serial_connected = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("视觉感知")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.camera_status_button = QtWidgets.QToolButton()
        self.camera_status_button.setObjectName("muted")
        self.camera_status_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.camera_status_button.setText("OV5640：等待状态")
        self.camera_status_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.camera_status_button.clicked.connect(self.toggle_camera_details)
        layout.addWidget(self.camera_status_button)

        self.camera_details = QtWidgets.QFrame()
        self.camera_details.setObjectName("cameraDetails")
        details_layout = QtWidgets.QFormLayout(self.camera_details)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_layout.setSpacing(6)
        self.camera_detail_label = QtWidgets.QLabel("等待 camera_status")
        self.camera_detail_label.setWordWrap(True)
        details_layout.addRow("设备详情", self.camera_detail_label)
        self.camera_details.setVisible(False)
        layout.addWidget(self.camera_details)

        self.detect_label = QtWidgets.QLabel("视觉模型：等待 ESP32-S3 后续接入")
        self.detect_label.setObjectName("muted")
        self.detect_label.setWordWrap(True)
        self.risk_label = QtWidgets.QLabel("ESP 风险：模块未接入")
        self.risk_label.setObjectName("muted")
        self.action_label = QtWidgets.QLabel("气囊策略：模块未接入")
        self.action_label.setObjectName("muted")
        for widget in (self.detect_label, self.risk_label, self.action_label):
            layout.addWidget(widget)

        layout.addStretch(1)

        self.camera_status_timer = QtCore.QTimer(self)
        self.camera_status_timer.setSingleShot(True)
        self.camera_status_timer.setInterval(self.CAMERA_STATUS_TIMEOUT_MS)
        self.camera_status_timer.timeout.connect(self._mark_camera_timeout)

    def set_serial_connected(self, connected: bool) -> None:
        self._serial_connected = connected
        self.camera_status_timer.stop()
        if connected:
            self._set_camera_status("OV5640：等待状态", "muted")
            self.camera_status_timer.start()
        else:
            self._set_camera_status("OV5640：等待状态", "muted")

    def update_camera_status(self, event: CameraStatusEvent) -> None:
        if not self._serial_connected:
            return

        self.camera_detail_label.setText(
            f"分辨率：{event.width}×{event.height}\n"
            f"格式：{event.pixel_format.upper()}\n"
            f"FPS：{event.fps:.1f}\n"
            f"帧大小：{event.frame_bytes} B\n"
            f"成功帧：{event.frames_ok}\n"
            f"失败次数：{event.capture_failures}\n"
            f"PSRAM：{'已启用' if event.psram else '未启用'}\n"
            f"最后更新：{event.ts_ms} ms"
        )
        if event.valid:
            self._set_camera_status("OV5640：状态正常", "statusOk")
        else:
            self._set_camera_status("OV5640：连接异常", "statusWarn")
        self.camera_status_timer.start()

    def toggle_camera_details(self) -> None:
        self.camera_details.setVisible(self.camera_details.isHidden())

    def _mark_camera_timeout(self) -> None:
        if self._serial_connected:
            self._set_camera_status("OV5640：连接异常", "statusWarn")

    def _set_camera_status(self, text: str, object_name: str) -> None:
        self.camera_status_button.setText(text)
        self.camera_status_button.setObjectName(object_name)
        self.camera_status_button.style().unpolish(self.camera_status_button)
        self.camera_status_button.style().polish(self.camera_status_button)
