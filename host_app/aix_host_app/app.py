from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from .models import ActuatorEvent, MotionEvent, PressureSample, RiskEvent, VisionDetectEvent
from .parsers import ParseError, parse_event_line
from .serial_source import SerialLineReader, list_serial_ports
from .simulation import make_simulated_pressure_sample
from .styles import app_stylesheet
from .vision import CameraFrame, CameraReader, CameraSourceConfig, VisionEventBridge, VisionTrendAnalyzer
from .widgets.connection_panel import ConnectionPanel
from .widgets.event_timeline import EventTimeline
from .widgets.motion_panel import MotionPanel
from .widgets.pressure_panel import PressurePanel
from .widgets.sensor_overview_panel import SensorOverviewPanel
from .widgets.vision_panel import VisionPanel


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("AIX 脉盔 | 上位机可视化")
        self.resize(1280, 780)
        self.setStyleSheet(app_stylesheet())

        self.reader: SerialLineReader | None = None
        self.camera_reader: CameraReader | None = None
        self.vision_analyzer = VisionTrendAnalyzer()
        self.vision_bridge = VisionEventBridge(min_interval_ms=100)
        self._camera_error_active = False
        self.record_file = None
        self.record_writer: csv.writer | None = None
        self.sim_seq = 0
        self.sim_clock = QtCore.QElapsedTimer()
        self.sim_timer = QtCore.QTimer(self)
        self.sim_timer.setInterval(500)
        self.sim_timer.timeout.connect(self._emit_simulated_sample)

        self.connection_panel = ConnectionPanel()
        self.overview_panel = SensorOverviewPanel()
        self.pressure_panel = PressurePanel()
        self.motion_panel = MotionPanel()
        self.vision_panel = VisionPanel()
        self.timeline = EventTimeline()

        self._build_layout()
        self._wire_signals()
        self.refresh_ports()
        self.statusBar().showMessage("就绪")

    def closeEvent(self, event) -> None:
        self._stop_camera(log=False)
        self._stop_serial()
        self._close_record_file()
        super().closeEvent(event)

    def refresh_ports(self) -> None:
        self.connection_panel.set_ports(list_serial_ports())

    def _build_layout(self) -> None:
        main_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        main_splitter.setChildrenCollapsible(False)
        main_splitter.addWidget(self.connection_panel)

        center = QtWidgets.QWidget()
        center_layout = QtWidgets.QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(8)
        center_layout.addWidget(self.overview_panel)

        sensor_splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        sensor_splitter.setChildrenCollapsible(False)
        sensor_splitter.addWidget(self.pressure_panel)
        sensor_splitter.addWidget(self.motion_panel)
        sensor_splitter.setSizes([620, 260])
        center_layout.addWidget(sensor_splitter, 1)
        center_layout.addWidget(self.timeline)

        main_splitter.addWidget(center)
        main_splitter.addWidget(self.vision_panel)
        main_splitter.setSizes([230, 820, 360])

        wrapper = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(wrapper)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.addWidget(main_splitter)
        self.setCentralWidget(wrapper)
    def _wire_signals(self) -> None:
        self.connection_panel.refresh_requested.connect(self.refresh_ports)
        self.connection_panel.connect_requested.connect(self._start_serial)
        self.connection_panel.disconnect_requested.connect(self._stop_serial)
        self.connection_panel.simulation_changed.connect(self._set_simulation_enabled)
        self.connection_panel.recording_changed.connect(self._set_recording_enabled)
        self.vision_panel.camera_start_requested.connect(self._start_camera)
        self.vision_panel.camera_stop_requested.connect(self._stop_camera)

    def _start_serial(self, port: str, baudrate: int) -> None:
        self._set_simulation_enabled(False)
        self.connection_panel.set_simulation_checked(False)
        self._stop_serial()
        self.pressure_panel.reset()
        self.timeline.add_line(f"[link] opening {port} @ {baudrate}")

        self.reader = SerialLineReader(port, baudrate, self)
        self.reader.line_received.connect(self._handle_raw_line)
        self.reader.error_changed.connect(self._handle_error)
        self.reader.state_changed.connect(self._handle_reader_state)
        self.reader.start()

    def _stop_serial(self) -> None:
        if self.reader is None:
            self.connection_panel.set_connected(False)
            return
        self.reader.stop()
        self.reader.wait(1500)
        self.reader = None
        self.connection_panel.set_connected(False)
        self.statusBar().showMessage("串口已断开")

    def _handle_reader_state(self, state: str) -> None:
        if state == "connected":
            self.connection_panel.set_connected(True, "串口双向已连接")
            self.statusBar().showMessage("正在接收 ESP 事件，可发送视觉特征")
        elif state == "disconnected":
            self.connection_panel.set_connected(False)
            self.statusBar().showMessage("串口未连接")

    def _handle_error(self, message: str) -> None:
        self.timeline.add_line(f"[error] {message}")
        self.connection_panel.set_status_text(message, warning=True)
        self.statusBar().showMessage(message)

    def _handle_raw_line(self, line: str) -> None:
        try:
            event = parse_event_line(line)
        except ParseError:
            if line.startswith("{"):
                self.timeline.add_line(f"[ignored] {line}")
            return

        if isinstance(event, PressureSample):
            self._accept_sample(event, raw_line=line)
        elif isinstance(event, MotionEvent):
            self.motion_panel.update_motion(event)
            self.overview_panel.update_motion(event)
            self.timeline.add_line(line)
        elif isinstance(event, RiskEvent):
            self.vision_panel.update_esp_risk(event)
            self.overview_panel.update_risk(event)
            self.timeline.set_summary(f"risk {event.level} | target {event.target_pct}% | {event.reason}")
            self.timeline.add_line(line)
        elif isinstance(event, ActuatorEvent):
            self.vision_panel.update_actuator(event)
            self.overview_panel.update_actuator(event)
            self.timeline.add_line(line)
        elif isinstance(event, VisionDetectEvent):
            self.vision_panel.update_vision_detect(event)
            self.timeline.add_line(line)

    def _accept_sample(self, sample: PressureSample, raw_line: str | None = None) -> None:
        self.pressure_panel.update_sample(sample)
        self.overview_panel.update_pressure(sample)
        self.timeline.set_summary(
            f"seq {sample.seq} | {sample.filtered_kpa:.1f} kPa | {sample.source}"
        )
        if raw_line:
            self.timeline.add_line(raw_line)
        else:
            self.timeline.add_line(
                f"[sim] seq={sample.seq}, filtered={sample.filtered_kpa:.1f}kPa"
            )
        self._record_sample(sample)

    def _start_camera(self, config: CameraSourceConfig) -> None:
        self._stop_camera(log=False)
        self._camera_error_active = False
        self.vision_analyzer = VisionTrendAnalyzer()
        self.vision_panel.set_placeholder_state()
        self.timeline.add_line(f"[camera] opening {config.source_label()}")

        self.camera_reader = CameraReader(config, self)
        self.camera_reader.frame_received.connect(self._handle_camera_frame)
        self.camera_reader.error_changed.connect(self._handle_camera_error)
        self.camera_reader.state_changed.connect(self._handle_camera_state)
        self.camera_reader.finished.connect(self._handle_camera_finished)
        self.camera_reader.start()
        self.vision_panel.set_camera_running(True, "正在打开摄像头")
        self.statusBar().showMessage("正在打开摄像头")

    def _stop_camera(self, log: bool = True) -> None:
        if self.camera_reader is None:
            self.vision_panel.set_camera_running(False)
            return

        reader = self.camera_reader
        self.camera_reader = None
        self._camera_error_active = False
        reader.stop()
        reader.wait(1500)
        self.vision_panel.set_camera_running(False)
        if log:
            self.timeline.add_line("[camera] stopped")
        self.statusBar().showMessage("摄像头已停止")

    def _handle_camera_state(self, state: str) -> None:
        if state == "connected":
            self._camera_error_active = False
            self.vision_panel.set_camera_running(True, "摄像头已连接")
            self.statusBar().showMessage("摄像头画面接收中")

    def _handle_camera_error(self, message: str) -> None:
        self._camera_error_active = True
        self.timeline.add_line(f"[camera:error] {message}")
        self.vision_panel.set_camera_error(message)
        self.statusBar().showMessage(message)

    def _handle_camera_finished(self) -> None:
        reader = self.sender()
        if reader is not self.camera_reader:
            return
        self.camera_reader = None
        if not self._camera_error_active:
            self.vision_panel.set_camera_running(False)

    def _handle_camera_frame(self, frame: CameraFrame) -> None:
        result = self.vision_analyzer.analyze(frame)
        self.vision_panel.update_frame(frame)
        self.vision_panel.update_analysis(result)
        now_ms = QtCore.QDateTime.currentMSecsSinceEpoch()
        failures_before = self.vision_bridge.status.failure_count
        sent = self.vision_bridge.maybe_send(result.features, self.reader, now_ms=now_ms)
        status = self.vision_bridge.status
        age_ms = None if status.last_sent_ms is None else max(0, now_ms - status.last_sent_ms)
        self.vision_panel.update_vision_tx_status(
            status.last_seq,
            age_ms,
            status.failure_count,
            connected=self.reader is not None,
        )
        if not sent and status.failure_count > failures_before:
            self.timeline.add_line("[vision:tx-fail] 串口写入视觉事件失败")


    def _set_simulation_enabled(self, enabled: bool) -> None:
        if enabled:
            self._stop_serial()
            self.pressure_panel.reset()
            self.sim_seq = 0
            self.sim_clock.restart()
            self.sim_timer.start()
            self.connection_panel.set_connected(False, "模拟数据")
            self.timeline.add_line("[sim] started")
            self.statusBar().showMessage("模拟数据运行中")
        else:
            self.sim_timer.stop()
            if self.reader is None:
                self.connection_panel.set_connected(False)

    def _emit_simulated_sample(self) -> None:
        self.sim_seq += 1
        sample = make_simulated_pressure_sample(self.sim_seq, self.sim_clock.elapsed())
        self._accept_sample(sample)

    def _set_recording_enabled(self, enabled: bool) -> None:
        if enabled:
            self._open_record_file()
        else:
            self._close_record_file()

    def _open_record_file(self) -> None:
        if self.record_file is not None:
            return
        logs_dir = Path(__file__).resolve().parents[1] / "logs"
        logs_dir.mkdir(exist_ok=True)
        filename = datetime.now().strftime("pressure_%Y%m%d_%H%M%S.csv")
        path = logs_dir / filename
        self.record_file = path.open("w", newline="", encoding="utf-8")
        self.record_writer = csv.writer(self.record_file)
        self.record_writer.writerow(
            ["seq", "ts_ms", "raw", "mv", "kpa", "filtered_kpa", "over_pressure", "valid", "source"]
        )
        self.timeline.add_line(f"[record] {path}")

    def _close_record_file(self) -> None:
        if self.record_file is None:
            return
        self.record_file.close()
        self.record_file = None
        self.record_writer = None
        self.timeline.add_line("[record] stopped")

    def _record_sample(self, sample: PressureSample) -> None:
        if self.record_writer is None:
            return
        self.record_writer.writerow(
            [
                sample.seq,
                sample.ts_ms,
                sample.raw,
                sample.mv,
                f"{sample.kpa:.3f}",
                f"{sample.filtered_kpa:.3f}",
                int(sample.over_pressure),
                int(sample.valid),
                sample.source,
            ]
        )
        if self.record_file is not None:
            self.record_file.flush()
