from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from .chain_client import PcChainClient
from .fonts import ensure_cjk_font
from .models import ActionStatusEvent, CameraStatusEvent, MotionEvent, PneumaticStatusEvent, PressureSample
from .parsers import ParseError, parse_event_line
from .serial_source import SerialLineReader, list_serial_ports
from .session_recorder import SessionRecorder
from .simulation import make_simulated_pressure_sample
from .styles import app_stylesheet
from .widgets.active_dashboard import ActiveVisionDashboard
from .widgets.connection_panel import ConnectionPanel


class MainWindow(QtWidgets.QMainWindow):
    """Industrial dashboard consuming the PC chain service plus ESP serial telemetry."""

    def __init__(self) -> None:
        super().__init__()
        ensure_cjk_font()
        self.setWindowTitle("AIX 主动视觉控制台")
        self.setMinimumSize(1280, 720)
        self.resize(1440, 900)
        self.setStyleSheet(app_stylesheet())

        settings = QtCore.QSettings("AIX", "HostApp")
        self.device_id = str(os.environ.get("AIX_DEVICE_ID") or settings.value("device_id", "aix-helmet-01"))
        self.service_url = str(os.environ.get("AIX_SERVICE_URL") or settings.value("service_url", "http://127.0.0.1:8008"))
        self.session_recorder = SessionRecorder(Path(settings.value("storage_root", r"F:\OV5640")))
        self.reader: SerialLineReader | None = None
        self._last_risk_identity: tuple[str, int] | None = None
        self._model_log_offsets: dict[Path, int] = {}
        self._last_chain_state: dict = {}
        self._chain_clock = QtCore.QElapsedTimer()
        self._chain_clock.start()
        self._watchdog_fault_shown = False
        self._last_pneumatic_boot = ""

        self.dashboard = ActiveVisionDashboard()
        wrapper = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(wrapper)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(self.dashboard)
        self.setCentralWidget(wrapper)

        self.connection_panel = ConnectionPanel()
        self.connection_panel.set_storage_root(str(self.session_recorder.root))
        self.settings_dialog = QtWidgets.QDialog(self)
        self.settings_dialog.setWindowTitle("设备与会话设置")
        self.settings_dialog.setMinimumWidth(420)
        settings_layout = QtWidgets.QVBoxLayout(self.settings_dialog)
        settings_layout.addWidget(self.connection_panel)

        self.chain_client = PcChainClient(self.service_url, self.device_id, self)
        self.chain_client.state_received.connect(self._accept_chain_state)
        self.chain_client.snapshot_received.connect(self._accept_pc_snapshot)
        self.chain_client.health_received.connect(self._accept_health)
        self.chain_client.error_changed.connect(self._accept_chain_error)
        self.chain_client.pneumatic_config_received.connect(self._accept_pneumatic_config)
        self.chain_client.pneumatic_command_finished.connect(self._accept_pneumatic_command)
        self.chain_client.pneumatic_error.connect(self._accept_pneumatic_error)

        self.sim_seq = 0
        self.sim_clock = QtCore.QElapsedTimer()
        self.sim_timer = QtCore.QTimer(self)
        self.sim_timer.setInterval(500)
        self.sim_timer.timeout.connect(self._emit_simulated_sample)
        self._watchdog_timer = QtCore.QTimer(self)
        self._watchdog_timer.setInterval(500)
        self._watchdog_timer.timeout.connect(self._check_chain_timeout)
        self._watchdog_timer.start()

        self._wire_settings()
        self.refresh_ports()
        self.dashboard.settings_requested.connect(self.settings_dialog.show)
        self.chain_client.start()
        self.statusBar().showMessage("上位机帧服务连接中；视觉模型将在后台加载")

    def _wire_settings(self) -> None:
        self.connection_panel.refresh_requested.connect(self.refresh_ports)
        self.connection_panel.connect_requested.connect(self._start_serial)
        self.connection_panel.disconnect_requested.connect(self._stop_serial)
        self.connection_panel.simulation_changed.connect(self._set_simulation_enabled)
        self.connection_panel.storage_root_changed.connect(self._set_storage_root)
        self.dashboard.pneumatic_panel.command_requested.connect(self.chain_client.send_pneumatic_command)
        self.dashboard.pneumatic_panel.config_requested.connect(self.chain_client.request_pneumatic_config)

    def closeEvent(self, event) -> None:
        self.chain_client.stop()
        self._stop_serial(close_session=False)
        self._capture_model_logs()
        self.session_recorder.close()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "dashboard"):
            self.dashboard.set_compact_mode(event.size().height() < 800)

    def refresh_ports(self) -> None:
        self.connection_panel.set_ports(list_serial_ports())

    def _ensure_session(self, serial_port: str = "PC-SERVICE", baudrate: int = 0) -> None:
        if self.session_recorder.session_dir is not None:
            return
        try:
            session = self.session_recorder.start(
                serial_port,
                baudrate,
                datetime.now().strftime("%Y%m%d_%H%M%S"),
            )
        except OSError as exc:
            self.connection_panel.set_status_text(f"记录目录不可写：{exc}", warning=True)
            return
        self.dashboard.set_session_path(str(session))

    def _start_serial(self, port: str, baudrate: int) -> None:
        self._set_simulation_enabled(False)
        self.connection_panel.set_simulation_checked(False)
        self._stop_serial(close_session=False)
        self.reader = SerialLineReader(port, baudrate, self)
        self.reader.line_received.connect(self._handle_raw_line)
        self.reader.error_changed.connect(self._handle_error)
        self.reader.state_changed.connect(self._handle_reader_state)
        self.reader.start()
        self._ensure_session(port, baudrate)

    def _stop_serial(self, *, close_session: bool = True) -> None:
        if self.reader is not None:
            self.reader.stop()
            self.reader.wait(1500)
            self.reader = None
        self.connection_panel.set_connected(False)
        if close_session:
            self.session_recorder.close()

    def _handle_reader_state(self, state: str) -> None:
        connected = state == "connected"
        self.connection_panel.set_connected(connected, "串口双向已连接" if connected else "串口未连接")
        self.statusBar().showMessage("头盔设备串口已连接" if connected else "头盔设备串口已断开")

    def _handle_error(self, message: str) -> None:
        self.connection_panel.set_status_text(message, warning=True)
        self.dashboard.protocol_log.appendPlainText(f"串口错误：{message}")

    def _handle_raw_line(self, line: str) -> None:
        self._ensure_session()
        self.session_recorder.record_event(line)
        try:
            event = parse_event_line(line)
        except ParseError:
            if line.startswith("{"):
                self.dashboard.protocol_log.appendPlainText(f"已忽略无法识别的协议消息：{line}")
            return
        if isinstance(event, PressureSample):
            self.session_recorder.record_pressure(event)
            self.dashboard.device_log.appendPlainText(
                f"压力数据：序号 {event.seq}，滤波值 {event.filtered_kpa:.2f} 千帕，"
                f"状态{'有效' if event.valid else '无效'}"
            )
        elif isinstance(event, CameraStatusEvent):
            self.dashboard.apply_camera_status(event)
        elif isinstance(event, ActionStatusEvent):
            self.dashboard.apply_action_status(event)
            self.session_recorder.record_action({
                "type": "action_status",
                "version": 1,
                "ts_ms": event.ts_ms,
                "frame_seq": event.frame_seq,
                "risk_score": event.risk_score,
                "valid": event.valid,
                "stale": event.stale,
                "action_state": event.action_state,
                "rgb_pattern": event.rgb_pattern,
            })
        elif isinstance(event, MotionEvent):
            if event.accel_norm_g is not None:
                self.dashboard.device_log.appendPlainText(
                    f"MPU6050：加速度 {event.accel_norm_g:.2f} g，倾角 {event.tilt_deg:.1f}°，"
                    f"冲击{'是' if event.impact else '否'}，快速倾斜{'是' if event.rapid_tilt else '否'}"
                )
            else:
                self.dashboard.device_log.appendPlainText("收到旧版运动诊断数据；不显示速度")
        elif isinstance(event, PneumaticStatusEvent):
            self.dashboard.apply_pneumatic_status(event)
            self.session_recorder.record_pneumatic({
                "type": "pneumatic_status", "version": 1, "ts_ms": event.ts_ms,
                "state": event.state, "fault": event.fault, "trigger": event.trigger,
                "operation": event.operation, "pump_on": event.pump_on, "valve_on": event.valve_on,
                "pressure_kpa": event.pressure_kpa, "pressure_valid": event.pressure_valid,
                "pressure_age_ms": event.pressure_age_ms, "vision_state": event.vision_state,
                "vision_fresh": event.vision_fresh, "mpu_available": event.mpu_available,
                "mpu_calibrated": event.mpu_calibrated, "impact": event.impact, "rapid_tilt": event.rapid_tilt,
            })

    def _accept_chain_state(self, state: dict) -> None:
        self._ensure_session()
        self._last_chain_state = state
        self._chain_clock.restart()
        self._watchdog_fault_shown = False
        self.dashboard.apply_chain_state(state)
        boot_id = str(state.get("boot_id") or "")
        if len(boot_id) == 16 and boot_id != self._last_pneumatic_boot:
            self._last_pneumatic_boot = boot_id
            self.chain_client.request_pneumatic_config()
        risk = state.get("risk", {})
        try:
            identity = (str(state.get("boot_id", "")), int(risk.get("frame_seq", -1)))
        except (TypeError, ValueError):
            identity = None
        if risk.get("valid") and identity is not None and identity != self._last_risk_identity:
            self._last_risk_identity = identity
            self.session_recorder.record_vision({
                "type": "vision_risk",
                "version": 1,
                "device_id": state.get("device_id"),
                "boot_id": state.get("boot_id"),
                "frame_seq": risk.get("frame_seq"),
                "risk_score": risk.get("score"),
                "risk_band": risk.get("band"),
                "reason": risk.get("reason"),
                "dominant_class": risk.get("dominant_class", ""),
                "model_latency_ms": state.get("model", {}).get("latency_ms"),
                "callback_latency_ms": state.get("callback", {}).get("latency_ms"),
                "valid": True,
            })

    def _accept_pneumatic_config(self, config: dict) -> None:
        self.dashboard.pneumatic_panel.apply_config(config)
        self._ensure_session()
        self.session_recorder.record_pneumatic_config(config)

    def _accept_pneumatic_command(self, payload: dict) -> None:
        self.dashboard.pneumatic_panel.apply_command_result(payload)
        self._ensure_session()
        self.session_recorder.record_pneumatic(payload)
        if payload.get("accepted") and payload.get("command_id"):
            self.chain_client.request_pneumatic_config()

    def _accept_pneumatic_error(self, message: str) -> None:
        self.dashboard.pneumatic_panel.show_error(message)
        self.dashboard.protocol_log.appendPlainText(message)

    def _accept_pc_snapshot(self, data: bytes, frame_seq: int, capture_ts_ms: int, state: dict) -> None:
        if not self.dashboard.apply_snapshot(data, frame_seq, capture_ts_ms, state):
            self.dashboard.protocol_log.appendPlainText("上位机帧服务返回了无效图像数据")
            return
        self._accept_chain_state(state)
        self._ensure_session()
        try:
            self.session_recorder.save_frame(data, frame_seq, capture_ts_ms)
        except OSError as exc:
            self.dashboard.protocol_log.appendPlainText(f"图像帧保存失败：{exc}")

    def _accept_health(self, health: dict) -> None:
        self.dashboard.apply_health(health)
        compute_label = "显卡" if str(health.get("gpu", "cuda")).lower() == "cuda" else "处理器"
        model_label = {"ready": "已就绪", "loading": "加载中", "error": "异常"}.get(
            str(health.get("model_state", "loading")), "状态未知"
        )
        line = (
            f"服务状态：模型{model_label}，运算设备{compute_label}，"
            f"异常信息：{health.get('model_error') or '无'}"
        )
        self.dashboard.chain_log.appendPlainText(line)
        if self.session_recorder.session_dir is not None:
            self.session_recorder.append_model_log(line)
            self._capture_model_logs()

    def _capture_model_logs(self) -> None:
        if self.session_recorder.session_dir is None:
            return
        for variable in ("AIX_MODEL_STDOUT_PATH", "AIX_MODEL_STDERR_PATH"):
            raw_path = os.environ.get(variable, "")
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            offset = min(self._model_log_offsets.get(path, 0), len(text))
            if len(text) > offset:
                self.session_recorder.append_model_log(f"[{path.name}]\n{text[offset:]}")
                self._model_log_offsets[path] = len(text)

    def _accept_chain_error(self, message: str) -> None:
        self.dashboard.protocol_log.appendPlainText(message)
        self.statusBar().showMessage(message)

    def _check_chain_timeout(self) -> None:
        if self._chain_clock.elapsed() < 3000 or self._watchdog_fault_shown:
            return
        previous = self._last_chain_state
        fault_state = {
            "type": "chain_state",
            "device_id": previous.get("device_id", self.device_id),
            "boot_id": previous.get("boot_id", ""),
            "upload": {**previous.get("upload", {}), "state": "failed", "fps": 0, "frame_age_ms": self._chain_clock.elapsed()},
            "model": {**previous.get("model", {}), "state": "error", "error": "PC 服务不可用"},
            "callback": {**previous.get("callback", {}), "state": "failed"},
            "risk": {**previous.get("risk", {}), "valid": False},
            "action": {**previous.get("action", {}), "state": "fault", "rgb_pattern": "purple_blink_1hz", "stale": True},
            "last_error": "PC 服务超过 3 秒无响应",
        }
        self.dashboard.apply_chain_state(fault_state)
        self._watchdog_fault_shown = True

    def _set_storage_root(self, path: str) -> None:
        self.session_recorder.root = Path(path)
        QtCore.QSettings("AIX", "HostApp").setValue("storage_root", path)

    def _set_simulation_enabled(self, enabled: bool) -> None:
        if enabled:
            self._stop_serial(close_session=False)
            self.sim_seq = 0
            self.sim_clock.restart()
            self.sim_timer.start()
            self.connection_panel.set_connected(False, "模拟数据")
        else:
            self.sim_timer.stop()

    def _emit_simulated_sample(self) -> None:
        self.sim_seq += 1
        sample = make_simulated_pressure_sample(self.sim_seq, self.sim_clock.elapsed())
        self._ensure_session()
        self.session_recorder.record_pressure(sample)
        self.dashboard.device_log.appendPlainText(
            f"sim pressure seq={sample.seq} filtered={sample.filtered_kpa:.2f}kPa"
        )
