from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from .chain_client import PcChainClient
from .fonts import ensure_cjk_font
from .models import ActionStatusEvent, CameraStatusEvent, HardwareHealthEvent, MotionEvent, PneumaticStatusEvent, PressureSample, RoadHazardStatusEvent, VoiceStatusEvent
from .parsers import ParseError, parse_event_line
from .serial_source import SerialLineReader, list_serial_ports, preferred_serial_port
from .session_recorder import SessionRecorder
from .styles import app_stylesheet
from .widgets.active_dashboard import ActiveVisionDashboard
from .widgets.cooperative_scenario import CooperativeScenarioPanel
from .widgets.connection_panel import ConnectionPanel


class MainWindow(QtWidgets.QMainWindow):
    """Industrial dashboard consuming the PC chain service plus ESP serial telemetry."""

    def __init__(self) -> None:
        super().__init__()
        ensure_cjk_font()
        self.setWindowTitle("AIX 主动视觉控制台")
        self.setMinimumSize(1024, 620)
        # Respect the logical work area under Windows DPI scaling; otherwise the
        # 1440×900 default can open clipped on a 1366×768-equivalent display.
        primary_screen = QtGui.QGuiApplication.primaryScreen()
        available = primary_screen.availableGeometry()
        scale = max(1.0, primary_screen.devicePixelRatio())
        available_width = int(available.width() / scale)
        available_height = int(available.height() / scale)
        self.resize(
            min(1440, max(self.minimumWidth(), available_width - 16)),
            min(900, max(self.minimumHeight(), available_height - 16)),
        )
        self.setStyleSheet(app_stylesheet())

        settings = QtCore.QSettings("AIX", "HostApp")
        self.device_id = str(os.environ.get("AIX_DEVICE_ID") or settings.value("device_id", "aix-helmet-01"))
        self.service_url = str(os.environ.get("AIX_SERVICE_URL") or settings.value("service_url", "http://127.0.0.1:8008"))
        self.session_recorder = SessionRecorder(Path(settings.value("storage_root", r"F:\OV5640")))
        self.reader: SerialLineReader | None = None
        self._closing = False
        self._serial_identity = str(settings.value("serial_identity", ""))
        self._auto_connect_serial = (
            os.environ.get("AIX_AUTO_CONNECT_SERIAL", "1") == "1" and
            QtGui.QGuiApplication.platformName() != "offscreen"
        )
        self._last_risk_identity: tuple[str, int] | None = None
        self._model_log_offsets: dict[Path, int] = {}
        self._last_chain_state: dict = {}
        self._chain_clock = QtCore.QElapsedTimer()
        self._chain_clock.start()
        self._watchdog_fault_shown = False
        self._last_pneumatic_boot = ""
        self._last_road_hazard_identity: tuple[str, str, str] | None = None

        self.dashboard = ActiveVisionDashboard()
        self.scenario_panel = CooperativeScenarioPanel()
        self.primary_pages = QtWidgets.QStackedWidget()
        self.primary_pages.setObjectName("primaryPages")
        self.primary_pages.addWidget(self.dashboard)
        self.primary_pages.addWidget(self.scenario_panel)
        # 默认轻量模式：中控保持一张已分析 PNG，避免串流画面拖慢上位机。
        self._reduce_motion = True
        self._page_opacity = QtWidgets.QGraphicsOpacityEffect(self.primary_pages)
        self.primary_pages.setGraphicsEffect(self._page_opacity)
        self._page_opacity.setOpacity(1.0)
        self._page_fade = QtCore.QPropertyAnimation(self._page_opacity, b"opacity", self)
        self._page_fade.setDuration(200)
        self._page_fade.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        wrapper = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(wrapper)
        layout.setContentsMargins(12, 10, 12, 8)
        layout.setSpacing(10)
        navigation = QtWidgets.QFrame()
        navigation.setObjectName("globalNavigation")
        nav_layout = QtWidgets.QHBoxLayout(navigation)
        nav_layout.setContentsMargins(16, 9, 12, 9)
        nav_layout.setSpacing(8)
        nav_title = QtWidgets.QLabel("AIX 控制中心")
        nav_title.setObjectName("appTitle")
        self.overview_button = QtWidgets.QPushButton("中控总览")
        self.scenario_button = QtWidgets.QPushButton("协同场景")
        for button in (self.overview_button, self.scenario_button):
            button.setCheckable(True)
        self.overview_button.setChecked(True)
        self.overview_button.clicked.connect(self._show_overview)
        self.scenario_button.clicked.connect(self._show_scenario)
        nav_layout.addWidget(nav_title)
        nav_layout.addSpacing(18)
        nav_layout.addWidget(self.overview_button)
        nav_layout.addWidget(self.scenario_button)
        nav_layout.addStretch(1)

        self.diagnostics_button = QtWidgets.QPushButton("诊断")
        self.diagnostics_button.setCheckable(True)
        self.diagnostics_button.toggled.connect(self._toggle_diagnostics)
        nav_layout.addWidget(self.diagnostics_button)

        self.session_button = QtWidgets.QToolButton()
        self.session_button.setText("会话记录")
        self.session_button.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        self.session_menu = QtWidgets.QMenu(self.session_button)
        self.session_state_action = self.session_menu.addAction("自动记录 · 已开启")
        self.session_state_action.setEnabled(False)
        self.session_root_action = self.session_menu.addAction(f"目录 · {self.session_recorder.root}")
        self.session_root_action.setEnabled(False)
        self.session_menu.addSeparator()
        self.choose_storage_action = self.session_menu.addAction("选择数据目录…")
        self.choose_storage_action.triggered.connect(self._choose_storage_root)
        self.session_button.setMenu(self.session_menu)
        nav_layout.addWidget(self.session_button)

        self.device_button = QtWidgets.QPushButton("● 设备未连接")
        self.device_button.setObjectName("deviceStatusButton")
        self.device_button.setCheckable(True)
        self.device_button.toggled.connect(self._set_device_sheet_visible)
        nav_layout.addWidget(self.device_button)
        layout.addWidget(navigation)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)
        content_layout.addWidget(self.primary_pages, 1)
        layout.addWidget(content, 1)
        self.setCentralWidget(wrapper)
        QtCore.QTimer.singleShot(0, self._place_in_available_geometry)

        self.connection_panel = ConnectionPanel()
        self.connection_panel.close_requested.connect(lambda: self.device_button.setChecked(False))
        self.device_window = QtWidgets.QDialog(
            self,
            QtCore.Qt.WindowType.Tool | QtCore.Qt.WindowType.FramelessWindowHint,
        )
        self.device_window.setObjectName("deviceWindow")
        self.device_window.setModal(False)
        self.device_window.setWindowTitle("设备接入")
        device_window_layout = QtWidgets.QVBoxLayout(self.device_window)
        device_window_layout.setContentsMargins(0, 0, 0, 0)
        device_window_layout.addWidget(self.connection_panel)
        self._device_opacity = QtWidgets.QGraphicsOpacityEffect(self.device_window)
        self.device_window.setGraphicsEffect(self._device_opacity)
        self._device_window_fade = QtCore.QPropertyAnimation(self._device_opacity, b"opacity", self)
        self._device_window_fade.setDuration(180)
        self._device_window_fade.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self.device_window.hide()

        # 诊断（含气动标定）必须脱离总览布局，避免压缩或覆盖中控画面。
        self.diagnostics_window = QtWidgets.QDialog(self, QtCore.Qt.WindowType.Tool)
        self.diagnostics_window.setObjectName("diagnosticsWindow")
        self.diagnostics_window.setModal(False)
        self.diagnostics_window.setWindowTitle("诊断与气动标定")
        diagnostics_layout = QtWidgets.QVBoxLayout(self.diagnostics_window)
        diagnostics_layout.setContentsMargins(12, 12, 12, 12)
        diagnostics_layout.addWidget(self.dashboard.diagnostics)
        self.diagnostics_window.resize(980, 650)
        self.diagnostics_window.finished.connect(self._diagnostics_window_finished)
        self.diagnostics_window.hide()

        self.chain_client = PcChainClient(
            self.service_url, self.device_id,
            token=str(os.environ.get("AIX_TOKEN") or settings.value("token", "")), parent=self,
        )
        self.chain_client.state_received.connect(self._accept_chain_state)
        self.chain_client.snapshot_received.connect(self._accept_pc_snapshot)
        self.chain_client.health_received.connect(self._accept_health)
        self.chain_client.error_changed.connect(self._accept_chain_error)
        self.chain_client.pneumatic_config_received.connect(self._accept_pneumatic_config)
        self.chain_client.pneumatic_command_finished.connect(self._accept_pneumatic_command)
        self.chain_client.pneumatic_error.connect(self._accept_pneumatic_error)
        self.chain_client.road_hazard_finished.connect(self._accept_road_hazard_submission)
        self.chain_client.road_hazard_error.connect(self._accept_road_hazard_error)

        self._watchdog_timer = QtCore.QTimer(self)
        self._watchdog_timer.setInterval(500)
        self._watchdog_timer.timeout.connect(self._check_chain_timeout)
        self._watchdog_timer.start()
        self._serial_reconnect_timer = QtCore.QTimer(self)
        self._serial_reconnect_timer.setInterval(2000)
        self._serial_reconnect_timer.timeout.connect(self.refresh_ports)
        self._serial_reconnect_timer.start()

        self._wire_settings()
        self.refresh_ports()
        self.scenario_panel.start_requested.connect(self.chain_client.send_road_hazard)
        self.scenario_panel.reset_requested.connect(self._record_road_hazard_reset)
        self.dashboard.set_static_visual_mode(False)
        # 协同场景只保留低频、必要的安全演示动作。
        self.scenario_panel.set_reduced_motion(True)
        self.chain_client.start()
        self.statusBar().showMessage("上位机帧服务连接中；视觉模型将在后台加载")

    def _wire_settings(self) -> None:
        self.connection_panel.refresh_requested.connect(self.refresh_ports)
        self.connection_panel.connect_requested.connect(self._start_serial)
        self.connection_panel.disconnect_requested.connect(self._stop_serial)
        self.dashboard.pneumatic_panel.command_requested.connect(self.chain_client.send_pneumatic_command)
        self.dashboard.pneumatic_panel.config_requested.connect(self.chain_client.request_pneumatic_config)

    def closeEvent(self, event) -> None:
        self._closing = True
        self._serial_reconnect_timer.stop()
        self.chain_client.stop()
        self._stop_serial(close_session=False)
        self._capture_model_logs()
        self.session_recorder.close()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "dashboard"):
            self.dashboard.set_compact_mode(event.size().height() < 800)

    def _place_in_available_geometry(self) -> None:
        """Center the first window in the current DPI-aware work area."""
        screen = self.screen() or QtGui.QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        scale = max(1.0, screen.devicePixelRatio())
        available_width = int(available.width() / scale)
        available_height = int(available.height() / scale)
        width = min(self.width(), max(self.minimumWidth(), available_width - 16))
        height = min(self.height(), max(self.minimumHeight(), available_height - 16))
        self.resize(width, height)
        self.move(
            int(available.left() / scale) + max(0, (available_width - width) // 2),
            int(available.top() / scale) + max(0, (available_height - height) // 2),
        )

    def _show_overview(self) -> None:
        self._set_primary_page(0)
        self.overview_button.setChecked(True)
        self.scenario_button.setChecked(False)

    def _show_scenario(self) -> None:
        self._set_primary_page(1)
        self.overview_button.setChecked(False)
        self.scenario_button.setChecked(True)

    def _set_primary_page(self, index: int) -> None:
        self._page_fade.stop()
        self.primary_pages.setCurrentIndex(index)
        self._page_opacity.setOpacity(1.0)

    def _toggle_diagnostics(self, enabled: bool) -> None:
        if not enabled:
            self.dashboard.diagnostics.hide()
            self.diagnostics_window.hide()
            return
        self._show_overview()
        self.dashboard.diagnostics.show()
        self.diagnostics_window.show()
        self.diagnostics_window.raise_()
        self.diagnostics_window.activateWindow()

    def _diagnostics_window_finished(self, _result: int) -> None:
        self.dashboard.diagnostics.hide()
        self.diagnostics_button.blockSignals(True)
        self.diagnostics_button.setChecked(False)
        self.diagnostics_button.blockSignals(False)

    def _set_device_sheet_visible(self, visible: bool) -> None:
        self._device_window_fade.stop()
        if not visible:
            self.device_window.hide()
            return
        self.device_window.adjustSize()
        width = max(420, self.device_window.sizeHint().width())
        height = self.device_window.sizeHint().height()
        self.device_window.resize(width, height)
        anchor = self.device_button.mapToGlobal(QtCore.QPoint(self.device_button.width() - width, self.device_button.height() + 8))
        screen = self.screen().availableGeometry()
        x = min(max(screen.left() + 8, anchor.x()), screen.right() - width - 8)
        y = min(max(screen.top() + 8, anchor.y()), screen.bottom() - height - 8)
        self.device_window.move(x, y)
        self.device_window.show()
        self.device_window.raise_()
        self._device_opacity.setOpacity(1.0)

    def _choose_storage_root(self) -> None:
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self, "选择会话数据目录", str(self.session_recorder.root)
        )
        if selected:
            self._set_storage_root(selected)
            self.session_root_action.setText(f"目录 · {selected}")

    def refresh_ports(self) -> None:
        options = list_serial_ports()
        self.connection_panel.set_ports(options)
        if self.reader is not None or self._closing or not self._auto_connect_serial:
            return
        preferred = preferred_serial_port(options, self._serial_identity)
        if preferred is None:
            return
        self._serial_identity = preferred.identity
        QtCore.QSettings("AIX", "HostApp").setValue("serial_identity", preferred.identity)
        QtCore.QTimer.singleShot(0, lambda: self._start_serial(preferred.device, 115200))

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
        self._stop_serial(close_session=False)
        self.reader = SerialLineReader(port, baudrate, self)
        self.reader.line_received.connect(self._handle_raw_line)
        self.reader.error_changed.connect(self._handle_error)
        self.reader.state_changed.connect(self._handle_reader_state)
        self.reader.start()
        self._ensure_session(port, baudrate)
        self.device_button.setText(f"● 正在连接 {port}")

    def _stop_serial(self, *, close_session: bool = True) -> None:
        if self.reader is not None:
            self.reader.stop()
            self.reader.wait(1500)
            self.reader = None
        self.connection_panel.set_connected(False)
        self.device_button.setText("● 设备未连接")
        if close_session:
            self.session_recorder.close()

    def _handle_reader_state(self, state: str) -> None:
        connected = state == "connected"
        self.connection_panel.set_connected(connected, "串口双向已连接" if connected else "串口未连接")
        self.device_button.setText(
            f"● {self.connection_panel.current_port()} 已连接" if connected else "● 设备未连接"
        )
        self.device_button.setProperty("connectionState", "connected" if connected else "disconnected")
        self.device_button.style().unpolish(self.device_button)
        self.device_button.style().polish(self.device_button)
        if connected:
            QtCore.QTimer.singleShot(260, lambda: self.device_button.setChecked(False))
        self.statusBar().showMessage("头盔设备串口已连接" if connected else "头盔设备串口已断开")
        if not connected and not self._closing:
            QtCore.QTimer.singleShot(500, self.refresh_ports)

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
            self.dashboard.apply_pressure(event)
            self.session_recorder.record_pressure(event)
            self.dashboard.device_log.appendPlainText(
                f"压力数据：序号 {event.seq}，滤波值 {event.filtered_kpa:.2f} 千帕，"
                f"状态{'有效' if event.valid else '无效'}"
            )
        elif isinstance(event, HardwareHealthEvent):
            self.dashboard.apply_hardware_health(event)
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
            self.dashboard.apply_motion(event)
            if event.accel_norm_g is not None:
                self.dashboard.device_log.appendPlainText(
                    f"MPU6050：加速度 {event.accel_norm_g:.2f} g，倾角 {event.tilt_deg:.1f}°，"
                    f"冲击{'是' if event.impact else '否'}，快速倾斜{'是' if event.rapid_tilt else '否'}"
                )
            else:
                self.dashboard.device_log.appendPlainText("收到旧版运动诊断数据；不显示速度")
        elif isinstance(event, PneumaticStatusEvent):
            self.dashboard.apply_pneumatic_status(event)
            self.scenario_panel.apply_pneumatic_status(event)
            self.session_recorder.record_pneumatic({
                "type": "pneumatic_status", "version": 1, "ts_ms": event.ts_ms,
                "state": event.state, "fault": event.fault, "trigger": event.trigger,
                "operation": event.operation, "pump_on": event.pump_on, "valve_on": event.valve_on,
                "pressure_kpa": event.pressure_kpa, "pressure_valid": event.pressure_valid,
                "pressure_age_ms": event.pressure_age_ms, "vision_state": event.vision_state,
                "vision_fresh": event.vision_fresh, "mpu_available": event.mpu_available,
                "mpu_calibrated": event.mpu_calibrated, "impact": event.impact, "rapid_tilt": event.rapid_tilt,
            })
        elif isinstance(event, VoiceStatusEvent):
            self.dashboard.apply_voice_status(event)
            self.scenario_panel.apply_voice_status(event)
            self.session_recorder.record_road_hazard({
                "type": "voice_status", "state": event.state, "command_id": event.command_id,
                "track": event.track, "error": event.error,
            })
        elif isinstance(event, RoadHazardStatusEvent):
            self._accept_road_hazard_status(event)

    def _accept_chain_state(self, state: dict) -> None:
        self._ensure_session()
        self._last_chain_state = state
        self._chain_clock.restart()
        self._watchdog_fault_shown = False
        self.dashboard.apply_chain_state(state)
        self.scenario_panel.apply_chain_state(state)
        hazard = state.get("road_hazard", {})
        if isinstance(hazard, dict) and hazard.get("event_id"):
            ack = hazard.get("ack", {}) if isinstance(hazard.get("ack"), dict) else {}
            identity = (
                str(hazard.get("event_id")), str(hazard.get("delivery", {}).get("state", "")),
                str(ack.get("state", "")),
            )
            if identity != self._last_road_hazard_identity:
                self._last_road_hazard_identity = identity
                self.session_recorder.record_road_hazard({"type": "road_hazard_chain", **hazard})
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

    def _accept_road_hazard_submission(self, payload: dict) -> None:
        self._ensure_session()
        self.session_recorder.record_road_hazard({"type": "road_hazard_submission", **payload})
        self.dashboard.protocol_log.appendPlainText(
            f"路侧协同事件已受理：{payload.get('event_id', '—')}；等待真实 ESP32 ACK"
        )

    def _accept_road_hazard_error(self, message: str) -> None:
        self._ensure_session()
        self.session_recorder.record_road_hazard({"type": "road_hazard_submission_error", "error": message})
        self.dashboard.protocol_log.appendPlainText(message)
        self.scenario_panel.apply_submission_error(message)
        self.statusBar().showMessage(message)

    def _accept_road_hazard_status(self, event: RoadHazardStatusEvent) -> None:
        self.scenario_panel.apply_serial_status(event)
        self.dashboard.protocol_log.appendPlainText(
            f"路侧预警串口状态：{event.state} · {event.event_id} · {event.effective_rgb_pattern or '无 RGB'}"
        )
        self._ensure_session()
        self.session_recorder.record_road_hazard({
            "type": "road_hazard_status", "state": event.state, "event_id": event.event_id,
            "severity": event.severity, "effective_rgb_pattern": event.effective_rgb_pattern, "reason": event.reason,
        })

    def _record_road_hazard_reset(self) -> None:
        self._ensure_session()
        self.session_recorder.record_road_hazard({"type": "road_hazard_reset"})

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
