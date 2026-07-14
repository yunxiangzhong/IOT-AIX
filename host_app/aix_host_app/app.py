from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from PySide6 import QtCore, QtWidgets

from .models import CameraPreviewEvent, CameraStatusEvent, MotionEvent, PressureSample, RiskAckEvent, VisionDepthEvent
from .parsers import ParseError, parse_event_line
from .serial_source import SerialLineReader, list_serial_ports
from .simulation import make_simulated_pressure_sample
from .styles import app_stylesheet
from .session_recorder import SessionRecorder
from .vision_client import ModelServiceManager, VisionInferenceClient
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
        self.record_file = None
        self.record_writer: csv.writer | None = None
        settings = QtCore.QSettings("AIX", "HostApp")
        self.session_recorder = SessionRecorder(Path(settings.value("storage_root", r"F:\OV5640")))
        self.model_service = ModelServiceManager(self)
        self.vision_client = VisionInferenceClient(self)
        self._risk_endpoint = ""
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
        self.connection_panel.set_storage_root(str(self.session_recorder.root))
        self.refresh_ports()
        self.statusBar().showMessage("就绪")

    def closeEvent(self, event) -> None:
        self._stop_serial()
        self.model_service.stop()
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
        self.connection_panel.storage_root_changed.connect(self._set_storage_root)
        self.vision_panel.frame_received.connect(self.vision_client.submit_frame)
        self.vision_client.frame_selected.connect(self._record_vision_frame)
        self.vision_client.risk_received.connect(lambda payload, _data: self._accept_vision_result(payload))
        self.vision_client.analysis_error.connect(lambda message: self.timeline.add_line(f"[vision] {message}"))
        self.vision_client.esp_sync_finished.connect(lambda ok, message: self.timeline.add_line(f"[risk] {message}"))
        self.model_service.ready_changed.connect(self._on_model_service_status)
        self.vision_panel.preview_endpoint_changed.connect(self._set_risk_endpoint)

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
        self.vision_panel.set_serial_connected(True)
        self._begin_session(port, baudrate)
        self.model_service.start()

    def _stop_serial(self) -> None:
        if self.reader is None:
            self.connection_panel.set_connected(False)
            self.vision_panel.set_serial_connected(False)
            self.session_recorder.close()
            self.vision_client.set_session_id("")
            self.model_service.stop()
            return
        self.reader.stop()
        self.reader.wait(1500)
        self.reader = None
        self.connection_panel.set_connected(False)
        self.vision_panel.set_serial_connected(False)
        self.session_recorder.close()
        self.vision_client.set_session_id("")
        self.model_service.stop()
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
        self.session_recorder.record_event(line)
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
        elif isinstance(event, CameraStatusEvent):
            self.vision_panel.update_camera_status(event)
            state = "正常" if event.valid else "异常"
            self.timeline.set_summary(f"OV5640 | {event.width}x{event.height} | {state}")
            self.timeline.add_line(line)
        elif isinstance(event, CameraPreviewEvent):
            self.vision_panel.update_camera_preview(event)
            self.timeline.set_summary("OV5640 画面预览已就绪" if event.valid else "OV5640 画面预览不可用")
            self.timeline.add_line(line)
        elif isinstance(event, VisionDepthEvent):
            self.vision_panel.update_vision_depth(event)
            state = "正常" if event.valid else "异常"
            self.timeline.set_summary(
                f"DA3 | 深度中位数 {event.depth_median:.3f} | {event.latency_ms:.0f} ms | {state}"
            )
            self.timeline.add_line(line)
        elif isinstance(event, RiskAckEvent):
            state = "已同步" if event.valid and not event.stale else "已过期"
            self.vision_panel.risk_label.setText(
                f"PC视觉风险：{event.risk_score}/100 | ESP {state}（帧 {event.frame_seq}）"
            )
            self.timeline.add_line(line)

    def _accept_sample(self, sample: PressureSample, raw_line: str | None = None) -> None:
        self.pressure_panel.update_sample(sample)
        self.overview_panel.update_pressure(sample)
        self.session_recorder.record_pressure(sample)
        summary = (f"seq {sample.seq} | {sample.filtered_kpa:.1f} kPa | {sample.source}"
                   if sample.valid else f"seq {sample.seq} | 压力无效 | {sample.source}")
        self.timeline.set_summary(summary)
        if raw_line:
            self.timeline.add_line(raw_line)
        else:
            self.timeline.add_line(
                f"[sim] seq={sample.seq}, filtered={sample.filtered_kpa:.1f}kPa"
            )
        if sample.valid:
            self._record_sample(sample)

    def _accept_vision_result(self, payload: dict) -> None:
        self.vision_panel.update_vision_risk(payload)
        self.overview_panel.update_vision_risk(payload)
        self.session_recorder.record_vision(payload)
        self.timeline.set_summary(
            f"PC视觉风险 {payload.get('risk_score', 0)}/100 | {payload.get('dominant_class') or '无分类目标'}"
        )
        self.timeline.add_line(
            f"[risk] frame={payload.get('frame_seq')} score={payload.get('risk_score')} reason={payload.get('reason')}"
        )
        if self._risk_endpoint:
            self.vision_client.send_risk_to_esp(
                self._risk_endpoint,
                {
                    "type": "host_risk",
                    "version": 1,
                    "frame_seq": int(payload.get("frame_seq", 0)),
                    "capture_ts_ms": int(payload.get("capture_ts_ms", 0)),
                    "risk_score": int(payload.get("risk_score", 0)),
                    "risk_band": str(payload.get("risk_band", "low")),
                    "dominant_class": str(payload.get("dominant_class", "")),
                    "valid": bool(payload.get("valid", False)),
                },
            )

    def _record_vision_frame(self, data: bytes, frame_seq: int, capture_ts_ms: int) -> None:
        if self.session_recorder.session_dir is None:
            return
        try:
            self.session_recorder.save_frame(data, frame_seq, capture_ts_ms)
        except OSError as exc:
            self.timeline.add_line(f"[record] 图像保存失败：{exc}")

    def _begin_session(self, port: str, baudrate: int) -> None:
        try:
            session = self.session_recorder.start(port, baudrate, datetime.now().strftime("%Y%m%d_%H%M%S"))
        except OSError as exc:
            self.connection_panel.set_status_text(f"记录目录不可写：{exc}", warning=True)
            self.timeline.add_line(f"[record] disabled: {exc}")
            return
        self.vision_client.set_session_id(session.name)
        self.timeline.add_line(f"[record] {session}")

    def _set_storage_root(self, path: str) -> None:
        self.session_recorder.root = Path(path)
        QtCore.QSettings("AIX", "HostApp").setValue("storage_root", path)
        if self.reader is not None:
            self._begin_session(self.reader._port, self.reader._baudrate)

    def _set_risk_endpoint(self, preview_url: str) -> None:
        self._risk_endpoint = preview_url[:-len("/capture.jpg")] + "/risk" if preview_url.endswith("/capture.jpg") else ""

    def _on_model_service_status(self, ready: bool, message: str) -> None:
        self.vision_client.set_service_ready(ready)
        self.timeline.add_line(f"[model] {message}")

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
