from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from ..serial_source import SerialPortOption


class ConnectionPanel(QtWidgets.QFrame):
    refresh_requested = QtCore.Signal()
    connect_requested = QtCore.Signal(str, int)
    disconnect_requested = QtCore.Signal()
    simulation_changed = QtCore.Signal(bool)
    recording_changed = QtCore.Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._connected = False

        self.port_combo = QtWidgets.QComboBox()
        self.baud_combo = QtWidgets.QComboBox()
        for rate in (115200, 230400, 256000, 921600):
            self.baud_combo.addItem(str(rate), rate)

        self.refresh_button = QtWidgets.QToolButton()
        self.refresh_button.setText("刷新")
        self.connect_button = QtWidgets.QPushButton("连接")
        self.connect_button.setProperty("primary", True)
        self.simulation_check = QtWidgets.QCheckBox("模拟数据")
        self.recording_check = QtWidgets.QCheckBox("记录 CSV")
        self.state_label = QtWidgets.QLabel("未连接")
        self.state_label.setObjectName("muted")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("链路")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        layout.addWidget(QtWidgets.QLabel("串口"))
        layout.addWidget(self.port_combo)
        layout.addWidget(self.refresh_button)
        layout.addWidget(QtWidgets.QLabel("波特率"))
        layout.addWidget(self.baud_combo)
        layout.addWidget(self.connect_button)
        layout.addSpacing(8)
        layout.addWidget(self.simulation_check)
        layout.addWidget(self.recording_check)
        layout.addStretch(1)
        layout.addWidget(self.state_label)

        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        self.connect_button.clicked.connect(self._toggle_connection)
        self.simulation_check.toggled.connect(self.simulation_changed.emit)
        self.recording_check.toggled.connect(self.recording_changed.emit)

    def set_ports(self, ports: list[SerialPortOption]) -> None:
        current_device = self.current_port()
        self.port_combo.clear()
        if not ports:
            self.port_combo.addItem("未检测到串口", "")
            return

        selected_index = 0
        for index, option in enumerate(ports):
            self.port_combo.addItem(option.label, option.device)
            if option.device == current_device:
                selected_index = index
        self.port_combo.setCurrentIndex(selected_index)

    def current_port(self) -> str:
        return str(self.port_combo.currentData() or "")

    def current_baudrate(self) -> int:
        return int(self.baud_combo.currentData())

    def set_connected(self, connected: bool, label: str | None = None) -> None:
        self._connected = connected
        self.connect_button.setText("断开" if connected else "连接")
        self.refresh_button.setEnabled(not connected)
        self.port_combo.setEnabled(not connected)
        self.baud_combo.setEnabled(not connected)
        self.simulation_check.setEnabled(not connected)
        self.state_label.setText(label or ("已连接" if connected else "未连接"))
        self.state_label.setObjectName("statusOk" if connected else "muted")
        self._refresh_label_style(self.state_label)

    def set_status_text(self, text: str, warning: bool = False) -> None:
        self.state_label.setText(text)
        self.state_label.setObjectName("statusWarn" if warning else "muted")
        self._refresh_label_style(self.state_label)

    def set_simulation_checked(self, checked: bool) -> None:
        self.simulation_check.blockSignals(True)
        self.simulation_check.setChecked(checked)
        self.simulation_check.blockSignals(False)

    def _toggle_connection(self) -> None:
        if self._connected:
            self.disconnect_requested.emit()
            return

        port = self.current_port()
        if not port:
            self.set_status_text("未选择串口", warning=True)
            return
        self.connect_requested.emit(port, self.current_baudrate())

    def _refresh_label_style(self, label: QtWidgets.QLabel) -> None:
        label.style().unpolish(label)
        label.style().polish(label)
