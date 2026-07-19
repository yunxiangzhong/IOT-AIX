from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..serial_source import SerialPortOption


class ConnectionPanel(QtWidgets.QFrame):
    """Non-modal device access sheet opened from the global device status control."""

    refresh_requested = QtCore.Signal()
    connect_requested = QtCore.Signal(str, int)
    disconnect_requested = QtCore.Signal()
    close_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("deviceSheet")
        self.setMinimumWidth(420)
        self.setMaximumWidth(460)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, QtWidgets.QSizePolicy.Policy.Preferred)
        self._connected = False

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(14)

        heading = QtWidgets.QHBoxLayout()
        title_box = QtWidgets.QVBoxLayout()
        title_box.setSpacing(2)
        title = QtWidgets.QLabel("设备接入")
        title.setObjectName("sheetTitle")
        subtitle = QtWidgets.QLabel("ESP32 串口与遥测来源")
        subtitle.setObjectName("muted")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        self.close_button = QtWidgets.QToolButton()
        self.close_button.setText("关闭")
        self.close_button.setAccessibleName("关闭设备接入面板")
        heading.addLayout(title_box, 1)
        heading.addWidget(self.close_button, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        root.addLayout(heading)

        port_heading = QtWidgets.QHBoxLayout()
        port_label = QtWidgets.QLabel("串口")
        port_label.setObjectName("fieldLabel")
        self.refresh_button = QtWidgets.QToolButton()
        self.refresh_button.setText("刷新")
        port_heading.addWidget(port_label)
        port_heading.addStretch(1)
        port_heading.addWidget(self.refresh_button)
        root.addLayout(port_heading)

        self.port_combo = QtWidgets.QComboBox()
        root.addWidget(self.port_combo)

        baud_label = QtWidgets.QLabel("波特率")
        baud_label.setObjectName("fieldLabel")
        self.baud_combo = QtWidgets.QComboBox()
        for rate in (115200, 230400, 256000, 921600):
            self.baud_combo.addItem(str(rate), rate)
        root.addWidget(baud_label)
        root.addWidget(self.baud_combo)

        self.connect_button = QtWidgets.QPushButton("连接设备")
        self.connect_button.setObjectName("primaryAction")
        root.addWidget(self.connect_button)

        state_card = QtWidgets.QFrame()
        state_card.setObjectName("sheetStateCard")
        state_layout = QtWidgets.QVBoxLayout(state_card)
        state_layout.setContentsMargins(12, 11, 12, 11)
        state_layout.setSpacing(4)
        state_caption = QtWidgets.QLabel("连接状态")
        state_caption.setObjectName("metricTitle")
        self.state_label = QtWidgets.QLabel("未连接")
        self.state_label.setObjectName("muted")
        self.state_label.setWordWrap(True)
        self.detail_label = QtWidgets.QLabel("等待选择可用串口")
        self.detail_label.setObjectName("monoMuted")
        self.detail_label.setWordWrap(True)
        state_layout.addWidget(state_caption)
        state_layout.addWidget(self.state_label)
        state_layout.addWidget(self.detail_label)
        root.addWidget(state_card)
        root.addStretch(1)

        note = QtWidgets.QLabel("连接设置只负责设备接入；会话记录和显示偏好位于顶部独立入口。")
        note.setObjectName("safetyNote")
        note.setWordWrap(True)
        root.addWidget(note)

        self.close_button.clicked.connect(self.close_requested.emit)
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.connect_button.clicked.connect(self._toggle_connection)

    def set_ports(self, ports: list[SerialPortOption]) -> None:
        current_device = self.current_port()
        self.port_combo.clear()
        if not ports:
            self.port_combo.addItem("未检测到串口", "")
            self.detail_label.setText("未发现串口，请检查 USB 连接后刷新")
            return
        selected_index = 0
        for index, option in enumerate(ports):
            self.port_combo.addItem(option.label, option.device)
            if option.device == current_device:
                selected_index = index
        self.port_combo.setCurrentIndex(selected_index)
        self.detail_label.setText(f"已发现 {len(ports)} 个串口")

    def current_port(self) -> str:
        return str(self.port_combo.currentData() or "")

    def current_baudrate(self) -> int:
        return int(self.baud_combo.currentData())

    def set_connected(self, connected: bool, label: str | None = None) -> None:
        self._connected = connected
        self.connect_button.setText("断开设备" if connected else "连接设备")
        self.refresh_button.setEnabled(not connected)
        self.port_combo.setEnabled(not connected)
        self.baud_combo.setEnabled(not connected)
        self.state_label.setText(label or ("已连接" if connected else "未连接"))
        self.state_label.setObjectName("statusOk" if connected else "muted")
        if connected:
            self.detail_label.setText(f"{self.current_port()} · {self.current_baudrate()} baud")
        self._refresh_label_style(self.state_label)

    def set_status_text(self, text: str, warning: bool = False) -> None:
        self.state_label.setText(text)
        self.state_label.setObjectName("statusWarn" if warning else "muted")
        self._refresh_label_style(self.state_label)

    def _toggle_connection(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
            return
        port = self.current_port()
        if not port:
            self.set_status_text("未选择串口", warning=True)
            return
        self.connect_requested.emit(port, self.current_baudrate())

    @staticmethod
    def _refresh_label_style(label: QtWidgets.QLabel) -> None:
        label.style().unpolish(label)
        label.style().polish(label)
