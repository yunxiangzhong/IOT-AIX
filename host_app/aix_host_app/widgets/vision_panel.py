from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..models import ActuatorEvent, RiskEvent, VisionDetectEvent
from ..vision import CameraFrame, CameraSourceConfig, VisionAnalysisResult


_PRESSURE_TEXT = {
    "disabled": "压力关闭",
    "safe": "压力正常",
    "unsafe": "压力异常",
    "enabled": "压力开启",
}


_REASON_TEXT = {
    "vision_missing": "ESP未收到视觉事件",
    "vision_stale": "ESP视觉过期",
    "vision_invalid": "视觉事件无效",
    "vision_clear": "接近趋势不足",
    "vision_weak": "弱接近",
    "vision_approach": "稳定接近",
    "vision_looming": "快速接近",
    "vision_critical": "极强接近",
}


class VisionPanel(QtWidgets.QFrame):
    camera_start_requested = QtCore.Signal(object)
    camera_stop_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._last_frame: CameraFrame | None = None
        self._running = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title = QtWidgets.QLabel("视觉感知")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        source_row = QtWidgets.QHBoxLayout()
        self.source_combo = QtWidgets.QComboBox()
        self.source_combo.addItem("本机摄像头", "local")
        self.source_combo.addItem("手机/IP 摄像头", "url")
        self.source_value = QtWidgets.QLineEdit("0")
        self.source_value.setPlaceholderText("0")
        source_row.addWidget(self.source_combo, 1)
        source_row.addWidget(self.source_value, 2)
        layout.addLayout(source_row)

        button_row = QtWidgets.QHBoxLayout()
        self.start_button = QtWidgets.QPushButton("启动摄像头")
        self.stop_button = QtWidgets.QPushButton("停止")
        self.stop_button.setEnabled(False)
        button_row.addWidget(self.start_button)
        button_row.addWidget(self.stop_button)
        layout.addLayout(button_row)

        self.state_label = QtWidgets.QLabel("摄像头未启动")
        self.state_label.setObjectName("muted")
        layout.addWidget(self.state_label)

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
        self.feature_label = QtWidgets.QLabel("视觉特征：等待画面")
        self.feature_label.setObjectName("muted")
        self.tx_label = QtWidgets.QLabel("视觉发送：等待串口和摄像头")
        self.tx_label.setObjectName("muted")
        self.risk_label = QtWidgets.QLabel("ESP风险等级 0")
        self.risk_label.setObjectName("statusOk")
        self.action_label = QtWidgets.QLabel("气囊策略：等待 ESP")
        self.action_label.setObjectName("muted")
        self.rule_label = QtWidgets.QLabel(
            "阈值：20=looming>=0.25；50=looming>=0.45且area>=0.20；"
            "80=looming>=0.70且area>=0.35；100=looming>=0.90且area>=0.60"
        )
        self.rule_label.setObjectName("muted")
        self.rule_label.setWordWrap(True)

        self.detect_label = QtWidgets.QLabel("目标检测：等待数据")
        self.detect_label.setObjectName("muted")
        self.detect_label.setWordWrap(True)

        for widget in (
            self.scene_label,
            self.target_label,
            self.feature_label,
            self.tx_label,
            self.risk_label,
            self.action_label,
            self.detect_label,
            self.rule_label,
        ):
            widget.setWordWrap(True)
            layout.addWidget(widget)

        layout.addStretch(1)

        self.source_combo.currentIndexChanged.connect(self._update_source_hint)
        self.start_button.clicked.connect(self._emit_start_requested)
        self.stop_button.clicked.connect(self.camera_stop_requested.emit)

    def current_config(self) -> CameraSourceConfig:
        kind = str(self.source_combo.currentData())
        value = self.source_value.text().strip()
        return CameraSourceConfig(kind=kind, value=value)

    def set_placeholder_state(self) -> None:
        self._last_frame = None
        self.frame.clear()
        self.frame.setText("Camera frame")
        self.scene_label.setText("场景：待接入")
        self.target_label.setText("目标：待接入")
        self.feature_label.setText("视觉特征：等待画面")
        self.tx_label.setText("视觉发送：等待串口和摄像头")
        self.risk_label.setText("ESP风险等级 0")
        self.risk_label.setObjectName("statusOk")
        self.action_label.setText("气囊策略：等待 ESP")
        self.detect_label.setText("目标检测：等待数据")
        self.detect_label.setObjectName("muted")
        self._refresh_label_style(self.risk_label)
        self._refresh_label_style(self.detect_label)

    def set_camera_running(self, running: bool, text: str | None = None) -> None:
        self._running = running
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.source_combo.setEnabled(not running)
        self.source_value.setEnabled(not running)
        self.state_label.setText(text or ("摄像头运行中" if running else "摄像头未启动"))
        self.state_label.setObjectName("statusOk" if running else "muted")
        self._refresh_label_style(self.state_label)

    def set_camera_error(self, message: str) -> None:
        self.set_camera_running(False, message)
        self.state_label.setObjectName("statusWarn")
        self._refresh_label_style(self.state_label)

    def update_frame(self, frame: CameraFrame) -> None:
        self._last_frame = frame
        self._render_frame(frame)

    def update_analysis(self, result: VisionAnalysisResult) -> None:
        self.scene_label.setText(f"场景：{result.scene}")
        self.target_label.setText(f"目标：{result.targets}")
        self.feature_label.setText(
            "视觉特征："
            f"扩张 {result.features.radial_expansion:.2f} | "
            f"looming {result.features.looming:.2f} | "
            f"中心 {result.features.center_motion:.2f} | "
            f"面积 {result.features.area_rate:.2f} | "
            f"置信 {result.features.confidence:.2f}"
        )

    def update_vision_tx_status(
        self,
        last_seq: int,
        last_sent_age_ms: int | None,
        failure_count: int,
        connected: bool,
    ) -> None:
        if not connected:
            text = "视觉发送：串口未连接"
        elif last_seq <= 0 or last_sent_age_ms is None:
            text = "视觉发送：等待第一帧发送"
        else:
            text = f"视觉发送：seq {last_seq} | {last_sent_age_ms} ms前 | 失败 {failure_count}"
        self.tx_label.setText(text)
        self.tx_label.setObjectName("statusWarn" if failure_count else "muted")
        self._refresh_label_style(self.tx_label)

    def update_esp_risk(self, event: RiskEvent) -> None:
        reason_text = _REASON_TEXT.get(event.reason, event.reason)
        stale_text = "，视觉过期" if event.vision_stale else ""
        pressure_text = f"，{_PRESSURE_TEXT.get(event.pressure_state, event.pressure_state)}"
        if not event.pressure_safe:
            pressure_text += "，气压保护"
        self.risk_label.setText(
            f"ESP风险等级 {event.level} -> 目标 {event.target_pct}% "
            f"({reason_text}{stale_text}{pressure_text})"
        )
        if event.level >= 80:
            object_name = "statusDanger"
        elif event.level > 0:
            object_name = "statusWarn"
        else:
            object_name = "statusOk"
        self.risk_label.setObjectName(object_name)
        self._refresh_label_style(self.risk_label)

    def update_actuator(self, event: ActuatorEvent) -> None:
        self.action_label.setText(
            f"气囊策略：{event.mode} | 目标 {event.target_pct}% | 泵 {event.pump} | 阀 {event.valve}"
        )
        self.action_label.setObjectName("statusWarn" if event.target_pct > 0 else "muted")
        self._refresh_label_style(self.action_label)

    def update_vision_detect(self, event: VisionDetectEvent) -> None:
        lines = [f"目标检测 [{event.source}] seq={event.seq}"]
        for obj in event.objects:
            lines.append(
                f"  {obj.class_name} {obj.confidence:.0%} | "
                f"距离 {obj.distance_m:.2f}m | "
                f"bbox({obj.bbox[0]},{obj.bbox[1]},{obj.bbox[2]},{obj.bbox[3]})"
            )
        lines.append(f"最近 {event.nearest_distance_m:.2f}m | TTC {event.ttc_s:.2f}s")
        self.detect_label.setText("\n".join(lines))
        warn = not event.valid or event.ttc_s < 1.0
        self.detect_label.setObjectName("statusWarn" if warn else "muted")
        self._refresh_label_style(self.detect_label)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._last_frame is not None:
            self._render_frame(self._last_frame)

    def _emit_start_requested(self) -> None:
        try:
            config = self.current_config()
            config.capture_input()
        except ValueError as exc:
            self.set_camera_error(str(exc))
            return
        self.camera_start_requested.emit(config)

    def _render_frame(self, frame: CameraFrame) -> None:
        image = QtGui.QImage(
            frame.rgb_data,
            frame.width,
            frame.height,
            frame.bytes_per_line,
            QtGui.QImage.Format.Format_RGB888,
        )
        pixmap = QtGui.QPixmap.fromImage(image.copy())
        scaled = pixmap.scaled(
            self.frame.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.frame.setPixmap(scaled)

    def _update_source_hint(self) -> None:
        kind = str(self.source_combo.currentData())
        if kind == "local":
            self.source_value.setPlaceholderText("0")
            if not self.source_value.text().strip():
                self.source_value.setText("0")
        else:
            self.source_value.setPlaceholderText("http://手机IP:端口/video 或 rtsp://...")
            if self.source_value.text().strip() == "0":
                self.source_value.clear()

    def _refresh_label_style(self, label: QtWidgets.QLabel) -> None:
        label.style().unpolish(label)
        label.style().polish(label)
