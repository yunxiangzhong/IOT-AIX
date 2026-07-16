from __future__ import annotations

import uuid

from PySide6 import QtCore, QtWidgets

from ..models import PneumaticStatusEvent


class PneumaticCalibrationPanel(QtWidgets.QWidget):
    """Manual-only pneumatic diagnostics; automatic mode has no UI switch."""

    command_requested = QtCore.Signal(dict)
    config_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        note = QtWidgets.QLabel(
            "仅用于接线后标定。自动响应只能由固件编译选项开启；本页没有自动模式开关。"
        )
        note.setWordWrap(True)
        note.setObjectName("safetyNote")
        layout.addWidget(note)

        self.status = QtWidgets.QLabel("气动状态：未从设备读取")
        self.status.setObjectName("sectionTitle")
        layout.addWidget(self.status)

        controls = QtWidgets.QGridLayout()
        self.target_kpa = QtWidgets.QDoubleSpinBox()
        self.target_kpa.setRange(2.0, 30.0)
        self.target_kpa.setDecimals(1)
        self.target_kpa.setValue(2.0)
        self.target_kpa.setSuffix(" kPa")
        self.max_kpa = QtWidgets.QDoubleSpinBox()
        self.max_kpa.setRange(4.0, 40.0)
        self.max_kpa.setDecimals(1)
        self.max_kpa.setValue(4.0)
        self.max_kpa.setSuffix(" kPa")
        self.max_inflate_ms = QtWidgets.QSpinBox()
        self.max_inflate_ms.setRange(200, 5000)
        self.max_inflate_ms.setValue(2000)
        self.max_inflate_ms.setSuffix(" ms")
        controls.addWidget(QtWidgets.QLabel("目标压力"), 0, 0)
        controls.addWidget(self.target_kpa, 0, 1)
        controls.addWidget(QtWidgets.QLabel("硬上限"), 1, 0)
        controls.addWidget(self.max_kpa, 1, 1)
        controls.addWidget(QtWidgets.QLabel("最大充气时长"), 2, 0)
        controls.addWidget(self.max_inflate_ms, 2, 1)
        layout.addLayout(controls)

        commands = QtWidgets.QGridLayout()
        self.pulse_button = QtWidgets.QPushButton("200 ms 充气脉冲")
        self.vent_button = QtWidgets.QPushButton("泄压")
        self.stop_button = QtWidgets.QPushButton("紧急停止")
        self.reset_button = QtWidgets.QPushButton("安全条件下复位锁存")
        self.save_button = QtWidgets.QPushButton("保存标定限制")
        self.refresh_button = QtWidgets.QPushButton("读取设备实际阈值")
        self.stop_button.setObjectName("dangerButton")
        for index, button in enumerate((self.pulse_button, self.vent_button, self.stop_button, self.reset_button, self.save_button, self.refresh_button)):
            commands.addWidget(button, index // 2, index % 2)
        layout.addLayout(commands)

        self.threshold_snapshot = QtWidgets.QPlainTextEdit("未从设备读取")
        self.threshold_snapshot.setReadOnly(True)
        self.threshold_snapshot.setMaximumBlockCount(100)
        layout.addWidget(self.threshold_snapshot, 1)

        self.pulse_button.clicked.connect(lambda: self._request("inflate_pulse"))
        self.vent_button.clicked.connect(lambda: self._request("vent"))
        self.stop_button.clicked.connect(lambda: self._request("emergency_stop"))
        self.reset_button.clicked.connect(lambda: self._request("reset_fault"))
        self.save_button.clicked.connect(self._save_calibration)
        self.refresh_button.clicked.connect(self.config_requested)

    @staticmethod
    def _command_id() -> str:
        return f"host-{uuid.uuid4().hex}"

    def _request(self, command: str) -> None:
        self.command_requested.emit({"command_id": self._command_id(), "command": command})

    def _save_calibration(self) -> None:
        self.command_requested.emit({
            "command_id": self._command_id(),
            "command": "save_calibration",
            "target_kpa": self.target_kpa.value(),
            "max_kpa": self.max_kpa.value(),
            "max_inflate_ms": self.max_inflate_ms.value(),
        })

    def apply_status(self, event: PneumaticStatusEvent) -> None:
        self.status.setText(
            f"气动状态：{event.state} · 故障：{event.fault} · 压力 {event.pressure_kpa:.2f} kPa · "
            f"泵{'开' if event.pump_on else '关'} / 阀{'通电' if event.valve_on else '断电泄压'}"
        )

    def apply_command_result(self, payload: dict) -> None:
        self.status.setText(
            f"命令结果：{'已接受' if payload.get('accepted') else '拒绝'} · "
            f"{payload.get('command_id', '无命令号')} · {payload.get('error') or '无错误'}"
        )

    def apply_config(self, config: dict) -> None:
        try:
            self.target_kpa.setValue(float(config["target_kpa"]))
            self.max_kpa.setValue(float(config["max_kpa"]))
            self.max_inflate_ms.setValue(int(config["max_inflate_ms"]))
        except (KeyError, TypeError, ValueError):
            self.threshold_snapshot.setPlainText("设备配置响应不完整，未更新当前限制。")
            return
        mpu = config.get("mpu", {}) if isinstance(config.get("mpu"), dict) else {}
        self.threshold_snapshot.setPlainText(
            "以下为从设备读取的实际阈值（不是界面预设）：\n"
            f"自动模式：{'已由固件启用' if config.get('automatic_enabled') else '固件关闭'}\n"
            f"已保存标定：{'是' if config.get('calibration_valid') else '否'}\n"
            f"压力：目标 {config.get('target_kpa')} kPa，硬上限 {config.get('max_kpa')} kPa，"
            f"最大充气 {config.get('max_inflate_ms')} ms，压力新鲜度 {config.get('pressure_stale_ms')} ms\n"
            f"时序：阀预开 {config.get('calibration_pulse_ms')} ms，保压最大 {config.get('hold_max_ms')} ms，"
            f"清除确认 {config.get('clear_confirm_ms')} ms，冷却 {config.get('cooldown_ms')} ms\n"
            f"MPU6050：{mpu.get('sample_hz')} Hz，冲击 {mpu.get('impact_g')} g × {mpu.get('impact_samples')}，"
            f"快速倾斜 {mpu.get('rapid_tilt_deg')}° / {mpu.get('rapid_tilt_dps')}°/s / {mpu.get('rapid_tilt_ms')} ms，"
            f"稳定清除 {mpu.get('clear_ms')} ms\n"
            f"引脚：泵 GPIO{config.get('pump_gpio')}，阀 GPIO{config.get('valve_gpio')}；"
            f"MPU SDA GPIO{mpu.get('sda_gpio')} / SCL GPIO{mpu.get('scl_gpio')} / INT GPIO{mpu.get('int_gpio')}"
        )

    def show_error(self, message: str) -> None:
        self.status.setText(f"气动通信失败：{message}")
