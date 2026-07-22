from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..collision_state import protection_readiness
from ..models import ActionStatusEvent, CameraStatusEvent, HardwareHealthEvent, MotionEvent, PneumaticStatusEvent, PressureSample, VoiceStatusEvent
from .pneumatic_calibration_panel import PneumaticCalibrationPanel
from .status_card import ClickableStatusCard
from .trend_dialog import TrendDialog, TrendStore
from .vision_canvas import VisionCanvas


STATUS_COLORS = {
    "loading": "#007AFF",
    "low": "#248A3D",
    "attention": "#A05A00",
    "high": "#C93400",
    "critical": "#D70015",
    "fault": "#8944AB",
}

STATE_LABELS = {
    "loading": "加载中", "ready": "已就绪", "healthy": "正常", "waiting": "等待中",
    "confirmed": "已确认", "failed": "失败", "error": "异常", "streaming": "采集中",
    "safe": "安全", "attention": "注意", "high": "高风险", "critical": "严重风险", "fault": "故障",
}

RISK_REASON_LABELS = {
    "scene_proximity": "前向场景接近程度升高，已根据目标与相对深度生成本帧判断。",
    "object_proximity": "前向目标接近程度升高，已根据目标与相对深度生成本帧判断。",
    "car_proximity": "前向车辆接近程度升高，已生成本帧视觉风险判断。",
    "car_approaching": "前向车辆正在接近，已生成本帧视觉风险判断。",
    "bus_proximity": "大型车辆接近程度升高，已生成本帧视觉风险判断。",
}

RGB_PATTERN_LABELS = {
    "blue_blink_1hz": "蓝灯慢闪", "green_solid": "绿灯常亮", "yellow_blink_1hz": "黄灯慢闪",
    "orange_blink_2hz": "橙灯快速闪烁", "red_double_pulse": "红灯双脉冲", "purple_blink_1hz": "紫灯慢闪",
}


def _state_label(value: object) -> str:
    return STATE_LABELS.get(str(value or "waiting"), "状态未知")


def _risk_reason_label(value: object, *, model_state: str, stale: bool) -> str:
    if stale:
        return "数据超过安全时效，旧风险已隔离；系统不会据此生成新的执行结论。"
    text = str(value or "")
    if text in RISK_REASON_LABELS:
        return RISK_REASON_LABELS[text]
    if model_state == "loading":
        return "视觉模型正在后台加载，系统会保留最新上传帧。"
    if not text:
        return "等待视觉模型给出与当前画面匹配的风险判断。"
    return "已生成本帧视觉风险判断，原始原因可在诊断信息中查看。"


def _rgb_pattern_label(value: object) -> str:
    return RGB_PATTERN_LABELS.get(str(value or ""), "灯光状态未知")


def _error_label(value: object) -> str:
    text = str(value or "")
    if not text:
        return "无异常"
    if "PC service" in text or "PC 服务" in text:
        return "上位机服务无响应"
    if "callback" in text.lower():
        return "结果回传失败"
    return "存在异常，打开诊断信息查看"


def _device_label(value: object) -> str:
    raw = str(value or "")
    suffix = raw.rsplit("-", 1)[-1]
    return f"头盔设备 {suffix.zfill(2)}" if suffix.isdigit() else "头盔设备"


class _RiskTrend(QtWidgets.QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.samples: list[int] = []
        self.setObjectName("riskTrend")
        self.setMinimumHeight(76)
        self.setAccessibleName("最近视觉风险趋势")

    def add_score(self, score: int) -> None:
        self.samples.append(max(0, min(100, int(score))))
        self.samples = self.samples[-48:]
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 7, -8, -8)
        if rect.width() <= 1 or rect.height() <= 1:
            return
        painter.setPen(QtGui.QPen(QtGui.QColor("#D2D2D7"), 1))
        for level in (30, 60, 80):
            y = rect.bottom() - (level / 100.0) * rect.height()
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))
        if not self.samples:
            painter.setPen(QtGui.QColor("#86868B"))
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "等待有效风险结果")
            return
        points = []
        for index, score in enumerate(self.samples):
            x = rect.left() if len(self.samples) == 1 else rect.left() + index * rect.width() / (len(self.samples) - 1)
            y = rect.bottom() - score * rect.height() / 100.0
            points.append(QtCore.QPointF(x, y))
        path = QtGui.QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.setPen(QtGui.QPen(QtGui.QColor("#007AFF"), 2))
        painter.drawPath(path)


class _Stage(QtWidgets.QFrame):
    """Non-visible state holder kept for protocol diagnostics and compatibility."""

    def __init__(self, index: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.title = QtWidgets.QLabel(title, self)
        self.meta = QtWidgets.QLabel("等待状态", self)
        self.dot = QtWidgets.QLabel("●", self)

    def set_state(self, meta: str, color: str) -> None:
        self.meta.setText(meta)
        self.dot.setStyleSheet(f"color: {color};")


class _StatusColumn(QtWidgets.QFrame):
    """Content-sized column; matching row count and stretch keep the causal chain aligned."""

    metric_clicked = QtCore.Signal(str)

    def __init__(self, object_name: str, title: str, rows: tuple[tuple[str, str], ...], *, clickable_keys: tuple[str, ...] = (), metric_aliases: dict[str, str] | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setMinimumWidth(0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Expanding)
        self.metric_aliases = metric_aliases or {}
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        heading = QtWidgets.QLabel(title)
        heading.setObjectName("columnTitle")
        layout.addWidget(heading)
        self.values: dict[str, QtWidgets.QLabel] = {}
        self.rows: dict[str, QtWidgets.QFrame] = {}
        for key, label in rows:
            block = ClickableStatusCard(key, label)
            block.set_trend_enabled(key in clickable_keys)
            block.clicked.connect(lambda key, aliases=self.metric_aliases: self.metric_clicked.emit(aliases.get(key, key)))
            value = block.value_label
            layout.addWidget(block, 1)
            self.values[key] = value
            self.rows[key] = block

    def set_value(self, key: str, value: str) -> None:
        block = self.rows.get(key)
        if isinstance(block, ClickableStatusCard):
            block.set_value(value)
            return
        if self.values[key].text() != value:
            self.values[key].setText(value)

    def set_tone(self, key: str, tone: str) -> None:
        block = self.rows.get(key)
        if block is None:
            return
        if isinstance(block, ClickableStatusCard):
            block.set_status(tone)
            return
        if block.property("statusTone") == tone:
            return
        block.setProperty("statusTone", tone)
        block.style().unpolish(block)
        block.style().polish(block)


class _HostStatusCard(QtWidgets.QFrame):
    def __init__(self, title: str, value: str, detail: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("hostStatusCard")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(11, 7, 11, 7)
        layout.setSpacing(3)
        caption = QtWidgets.QLabel(title)
        caption.setObjectName("metricTitle")
        self.value = QtWidgets.QLabel(value)
        self.value.setObjectName("hostStatusValue")
        self.value.setWordWrap(True)
        self.detail = QtWidgets.QLabel(detail)
        self.detail.setObjectName("monoMuted")
        self.detail.setWordWrap(True)
        layout.addWidget(caption)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)


class ActiveVisionDashboard(QtWidgets.QWidget):
    settings_requested = QtCore.Signal()

    ROWS = (
        ("ov5640", "OV5640 摄像头"),
        ("mpu6050", "MPU6050"),
        ("pressure", "压力传感器"),
        ("dfplayer", "DFPlayer"),
        ("rgb", "RGB 警示灯"),
        ("pneumatic", "气泵 · 阀门 · 气囊"),
    )

    DISPLAY_OWNERS = {
        **{("peripheralPanel", key): "hardware_health" for key, _ in ROWS},
        ("realtimePanel", "ov5640"): "chain_state",
        ("realtimePanel", "mpu6050"): "motion",
        ("realtimePanel", "pressure"): "pressure",
        ("realtimePanel", "dfplayer"): "voice_status",
        ("realtimePanel", "rgb"): "chain_state",
        ("realtimePanel", "pneumatic"): "pneumatic_status",
        ("decisionPanel", "ov5640"): "chain_state",
        ("decisionPanel", "mpu6050"): "chain_state",
        ("decisionPanel", "pressure"): "pneumatic_status",
        ("decisionPanel", "dfplayer"): "voice_status",
        ("decisionPanel", "rgb"): "chain_state",
        ("decisionPanel", "pneumatic"): "pneumatic_status",
    }

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("activeDashboard")
        self._last_state: dict = {}
        self._last_trend_frame = -1
        self._last_display_frame_seq = -1
        self._static_visual_mode = False
        self._last_state_revision: int | None = None
        self._sensor_received_at_ms: dict[str, int] = {}
        self._sensor_source_ts_ms: dict[str, int] = {}
        self._last_pressure_sample: PressureSample | None = None
        self._pneumatic_fault = "none"
        self.trend_store = TrendStore()
        self.trend_dialog = TrendDialog(self)
        self._pending_display_updates: dict[tuple[str, str], tuple[str, str | None]] = {}
        self._display_cache: dict[tuple[str, str], tuple[str, str | None]] = {}
        self._compact = False
        self.sensor_row_keys = tuple(key for key, _ in self.ROWS)
        self.workspace_ratios = (11, 3, 3, 4)

        self._init_stage_holders()
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(self._build_workspace(), 1)
        self.diagnostics = self._build_diagnostics()
        self.diagnostics.hide()

        self.risk_trend = _RiskTrend(self)
        self.risk_trend.hide()
        self._sensor_freshness_timer = QtCore.QTimer(self)
        self._sensor_freshness_timer.setInterval(500)
        self._sensor_freshness_timer.timeout.connect(self.refresh_sensor_freshness)
        self._sensor_freshness_timer.start()
        self._display_timer = QtCore.QTimer(self)
        self._display_timer.setInterval(500)
        self._display_timer.timeout.connect(self._flush_display_updates)
        self._display_timer.start()

    def _init_stage_holders(self) -> None:
        self.camera_stage = _Stage("01", "相机采集", self)
        self.upload_stage = _Stage("02", "图像上传", self)
        self.model_stage = _Stage("03", "上位机视觉推理", self)
        self.action_stage = _Stage("04", "动作反馈", self)
        for stage in (self.camera_stage, self.upload_stage, self.model_stage, self.action_stage):
            stage.hide()
        self.instrument_subtitle = QtWidgets.QLabel("主动视觉闭环监控", self)
        self.instrument_subtitle.hide()

    def _build_workspace(self) -> QtWidgets.QWidget:
        workspace = QtWidgets.QWidget()
        workspace.setObjectName("workspaceSplitter")
        layout = QtWidgets.QHBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        camera = self._build_camera_panel()
        right = QtWidgets.QWidget()
        right.setObjectName("rightControlSurface")
        right_layout = QtWidgets.QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)

        mapping = QtWidgets.QWidget()
        mapping_layout = QtWidgets.QHBoxLayout(mapping)
        mapping_layout.setContentsMargins(0, 0, 0, 0)
        mapping_layout.setSpacing(8)
        peripheral_rows = self.ROWS
        realtime_rows = (
            ("ov5640", "目标 · 相对风险"), ("mpu6050", "加速度 · 倾角 · 冲击"),
            ("pressure", "压力 · 当前值"), ("dfplayer", "播放状态 · 曲目"),
            ("rgb", "模式 · 亮度"), ("pneumatic", "泵阀 · 压力反馈"),
        )
        derived_rows = (
            ("ov5640", "危险等级"), ("mpu6050", "气囊充气建议"),
            ("pressure", "气动允许 / 禁止原因"), ("dfplayer", "语音实际反馈"),
            ("rgb", "灯光实际反馈"), ("pneumatic", "泵阀真实反馈"),
        )
        self.peripheral_panel = _StatusColumn(
            "peripheralPanel", "感知与外设", peripheral_rows,
            clickable_keys=("ov5640",), metric_aliases={"ov5640": "upload_fps"},
        )
        self.realtime_panel = _StatusColumn(
            "realtimePanel", "实时数据", realtime_rows,
            clickable_keys=("ov5640", "mpu6050", "pressure"),
            metric_aliases={"ov5640": "risk_score", "mpu6050": "motion", "pressure": "pressure_kpa"},
        )
        self.decision_panel = _StatusColumn("decisionPanel", "推导与执行", derived_rows)
        self.peripheral_values = self.peripheral_panel.values
        self.realtime_values = self.realtime_panel.values
        self.derived_values = self.decision_panel.values
        self.derived_rows = self.decision_panel.rows
        self.peripheral_panel.metric_clicked.connect(self._show_trend)
        self.realtime_panel.metric_clicked.connect(self._show_trend)
        mapping_layout.addWidget(self.peripheral_panel, 3)
        mapping_layout.addWidget(self.realtime_panel, 3)
        mapping_layout.addWidget(self.decision_panel, 4)
        right_layout.addWidget(mapping, 1)

        guard = QtWidgets.QFrame()
        guard.setObjectName("guardBar")
        guard_layout = QtWidgets.QVBoxLayout(guard)
        guard_layout.setContentsMargins(12, 8, 12, 8)
        guard_layout.setSpacing(2)
        self.risk_reason = QtWidgets.QLabel("等待视觉模型给出与当前画面匹配的风险判断。")
        self.risk_reason.setObjectName("guardPrimary")
        self.risk_reason.setWordWrap(True)
        self.execution_guard = QtWidgets.QLabel("旧数据、断链或无效数据不会生成新的执行结论。")
        self.execution_guard.setObjectName("safetyNote")
        self.execution_guard.setWordWrap(True)
        self.pneumatic_acceptance_note = QtWidgets.QLabel("策略建议与真实执行严格分开；气囊结论以泵阀和压力反馈为准。")
        self.pneumatic_acceptance_note.setObjectName("safetyNote")
        self.pneumatic_acceptance_note.setWordWrap(True)
        guard_layout.addWidget(self.risk_reason)
        guard_layout.addWidget(self.execution_guard)
        guard_layout.addWidget(self.pneumatic_acceptance_note)
        right_layout.addWidget(guard)
        right_layout.addWidget(self._build_upper_status())

        self._set_initial_mapping_values()
        self.camera_panel = camera
        camera.setMinimumWidth(520)
        right.setMinimumWidth(570)
        camera.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        right.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        # A splitter enforces a finite allocation: the video canvas may never grow
        # past the point where the three causal columns disappear off-screen.
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setObjectName("workspacePaneSplitter")
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(camera)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 13)
        splitter.setStretchFactor(1, 9)
        splitter.setSizes([820, 520])
        self.workspace_pane_splitter = splitter
        layout.addWidget(splitter, 1)
        return workspace

    def _build_camera_panel(self) -> QtWidgets.QFrame:
        camera = QtWidgets.QFrame()
        camera.setObjectName("visionPanel")
        layout = QtWidgets.QVBoxLayout(camera)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        head = QtWidgets.QFrame()
        head.setObjectName("panelHead")
        head_layout = QtWidgets.QHBoxLayout(head)
        head_layout.setContentsMargins(16, 10, 16, 10)
        title = QtWidgets.QLabel("已分析视觉画面")
        title.setObjectName("panelTitle")
        self.camera_state_badge = QtWidgets.QLabel("● 等待画面")
        self.camera_state_badge.setObjectName("softBadge")
        self.frame_telemetry = QtWidgets.QLabel("等待上位机已分析帧")
        self.frame_telemetry.setObjectName("monoMuted")
        self.frame_telemetry.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        head_layout.addWidget(title)
        head_layout.addWidget(self.camera_state_badge)
        head_layout.addWidget(self.frame_telemetry, 1)
        self.camera_image = VisionCanvas()
        footer = QtWidgets.QFrame()
        footer.setObjectName("cameraFooter")
        footer_layout = QtWidgets.QHBoxLayout(footer)
        footer_layout.setContentsMargins(16, 7, 16, 7)
        footer_layout.setSpacing(18)
        self.camera_source = QtWidgets.QLabel("来源 · 头盔 OV5640")
        self.camera_health = QtWidgets.QLabel("采集 · 等待连接")
        self.camera_uplink = QtWidgets.QLabel("上传 · 等待首帧")
        for label in (self.camera_source, self.camera_health, self.camera_uplink):
            label.setObjectName("cameraTelemetry")
            footer_layout.addWidget(label)
        footer_layout.addStretch(1)
        layout.addWidget(head)
        layout.addWidget(self.camera_image, 1)
        layout.addWidget(footer)
        return camera

    def _build_upper_status(self) -> QtWidgets.QFrame:
        panel = QtWidgets.QFrame()
        panel.setObjectName("upperComputerPanel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(7)
        heading = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("上位机状态")
        title.setObjectName("columnTitle")
        self.safety_note = QtWidgets.QLabel("本地服务、GPU、模型与协同链路")
        self.safety_note.setObjectName("muted")
        heading.addWidget(title)
        heading.addStretch(1)
        heading.addWidget(self.safety_note)
        layout.addLayout(heading)
        cards = QtWidgets.QHBoxLayout()
        cards.setSpacing(5)
        self.host_service_card = _HostStatusCard("服务", "● 启动中", "等待健康检查")
        self.device_card = _HostStatusCard("设备链路", "等待连接", "等待视觉帧")
        self.model_card = _HostStatusCard("CUDA 与模型", "加载中", "DA3 / YOLO")
        self.cloud_card = _HostStatusCard("协同链路", "本地服务链路", "等待真实设备回传")
        for card in (self.host_service_card, self.device_card, self.model_card, self.cloud_card):
            cards.addWidget(card, 1)
        layout.addLayout(cards)
        self.system_status = self.host_service_card.value
        self.device_value = self.device_card.value
        self.model_value = self.model_card.value
        self.cloud_value = self.cloud_card.value
        self.decision_freshness = self.host_service_card.detail
        self.decision_frame = self.device_card.detail
        self.decision_model = self.model_card.detail
        self.decision_callback = self.cloud_card.detail
        self.decision_counts = QtWidgets.QLabel("接收 0 · 分析 0 · 确认 0", self)
        self.decision_counts.hide()
        self.risk_score = QtWidgets.QLabel("--", self)
        self.risk_score.hide()
        self.risk_band = QtWidgets.QLabel("模型加载中", self)
        self.risk_band.hide()
        self.result_state = QtWidgets.QLabel("● 等待模型", self)
        self.result_state.hide()
        self.action_name = QtWidgets.QLabel("启动提示", self)
        self.action_name.hide()
        self.action_ack = QtWidgets.QLabel("等待动作确认", self)
        self.action_ack.hide()
        return panel

    def _set_initial_mapping_values(self) -> None:
        for key in self.sensor_row_keys:
            self.peripheral_panel.set_value(key, "未连接\n等待设备数据")
            self.realtime_panel.set_value(key, "等待数据")
            self.decision_panel.set_value(key, "等待有效反馈")
        self.voice_status_value = self.derived_values["dfplayer"]
        self.action_pattern = self.derived_values["rgb"]
        self.pneumatic_summary = self.derived_values["pneumatic"]

    def _build_diagnostics(self) -> QtWidgets.QTabWidget:
        tabs = QtWidgets.QTabWidget()
        tabs.setObjectName("diagnostics")
        self.chain_log = QtWidgets.QPlainTextEdit()
        self.protocol_log = QtWidgets.QPlainTextEdit()
        self.device_log = QtWidgets.QPlainTextEdit("OV5640：等待链路\nMPU6050：等待串口\n压力传感器：等待串口\nDFPlayer / RGB / 气动总成：等待串口")
        self.session_log = QtWidgets.QPlainTextEdit("会话尚未开始")
        for widget in (self.chain_log, self.protocol_log, self.device_log, self.session_log):
            widget.setReadOnly(True)
            widget.setMaximumBlockCount(500)
        tabs.addTab(self.chain_log, "链路")
        tabs.addTab(self.protocol_log, "协议")
        tabs.addTab(self.device_log, "设备")
        self.pneumatic_panel = PneumaticCalibrationPanel()
        tabs.addTab(self.pneumatic_panel, "气动标定")
        tabs.addTab(self.session_log, "会话")
        return tabs

    def set_diagnostic_mode(self, enabled: bool) -> None:
        self.diagnostics.setVisible(enabled)

    def _queue_mapping_value(
        self,
        panel: _StatusColumn,
        key: str,
        value: str,
        *,
        source: str,
        immediate: bool = False,
        tone: str | None = None,
    ) -> bool:
        cache_key = (panel.objectName(), key)
        if self.DISPLAY_OWNERS.get(cache_key) != source:
            return False
        display_state = (value, tone)
        if self._pending_display_updates.get(cache_key) == display_state:
            return False
        if cache_key not in self._pending_display_updates and self._display_cache.get(cache_key) == display_state:
            return False
        if immediate or cache_key not in self._display_cache:
            panel.set_value(key, value)
            self._display_cache[cache_key] = display_state
            self._pending_display_updates.pop(cache_key, None)
            if tone:
                panel.set_tone(key, tone)
            return True
        self._pending_display_updates[cache_key] = display_state
        return True

    def _flush_display_updates(self) -> None:
        pending = self._pending_display_updates
        self._pending_display_updates = {}
        panels = {
            self.peripheral_panel.objectName(): self.peripheral_panel,
            self.realtime_panel.objectName(): self.realtime_panel,
            self.decision_panel.objectName(): self.decision_panel,
        }
        for (panel_name, key), (value, tone) in pending.items():
            panel = panels.get(panel_name)
            if panel is None:
                continue
            panel.set_value(key, value)
            self._display_cache[(panel_name, key)] = (value, tone)
            if tone:
                panel.set_tone(key, tone)

    def _record_trend(self, metric_key: str, timestamp_ms: int, value: float, label: str = "") -> None:
        self.trend_store.add(metric_key, timestamp_ms, value, label)
        if self.trend_dialog.isVisible() and self.trend_dialog._metric_key in {metric_key, "motion"}:
            self.trend_dialog.refresh_plot()

    def _show_trend(self, metric_key: str) -> None:
        if metric_key == "risk_score":
            self.trend_dialog.set_metric("risk_score", "视觉风险", "分", self.trend_store)
        elif metric_key == "motion":
            self.trend_dialog.set_metric("motion", "MPU6050 姿态趋势", "", self.trend_store)
        elif metric_key == "pressure_kpa":
            self.trend_dialog.set_metric("pressure_kpa", "压力趋势", "kPa", self.trend_store)
        elif metric_key == "upload_fps":
            self.trend_dialog.set_metric("upload_fps", "OV5640 上传速率", "帧/秒", self.trend_store)
        else:
            self.trend_dialog.set_metric(metric_key, metric_key, "", self.trend_store)
        self.trend_dialog.show()
        self.trend_dialog.raise_()
        self.trend_dialog.activateWindow()

    def set_static_visual_mode(self, enabled: bool) -> None:
        """Keep the latest analysed PNG on screen while telemetry continues to refresh."""
        self._static_visual_mode = bool(enabled)

    def set_compact_mode(self, compact: bool) -> None:
        self._compact = compact
        self.safety_note.setVisible(not compact)
        for panel in (self.peripheral_panel, self.realtime_panel, self.decision_panel):
            for row_frame in panel.rows.values():
                if hasattr(row_frame, "secondary_label"):
                    row_frame.secondary_label.setVisible(not compact)
        self.risk_trend.hide()

    def workspace_column_widths(self) -> tuple[int, int, int, int]:
        return self.camera_panel.width(), self.peripheral_panel.width(), self.realtime_panel.width(), self.decision_panel.width()

    def sensor_mapping_row_geometries(self) -> tuple[tuple[QtCore.QRect, QtCore.QRect, QtCore.QRect], ...]:
        def mapped(widget: QtWidgets.QWidget) -> QtCore.QRect:
            return QtCore.QRect(widget.mapTo(self, QtCore.QPoint(0, 0)), widget.size())
        return tuple(
            (mapped(self.peripheral_panel.rows[key]), mapped(self.realtime_panel.rows[key]), mapped(self.decision_panel.rows[key]))
            for key in self.sensor_row_keys
        )

    def _set_system_status(self, text: str, band: str) -> None:
        color = STATUS_COLORS.get(band, STATUS_COLORS["loading"])
        self.system_status.setText(f"● {text}")
        self.system_status.setStyleSheet(f"color: {color}; background: transparent; font-weight: 650;")

    def apply_frame(self, data: bytes, frame_seq: int, capture_ts_ms: int) -> bool:
        if not (self._static_visual_mode and self._last_display_frame_seq >= 0):
            if not self.camera_image.set_snapshot(data, []):
                return False
        self._last_display_frame_seq = frame_seq
        prefix = "固定画面 · " if self._static_visual_mode else ""
        self.frame_telemetry.setText(f"{prefix}第 {frame_seq:08d} 帧 · 采集 {capture_ts_ms} ms")
        self.camera_state_badge.setText("● 分析完成")
        self.camera_state_badge.setProperty("state", "ok")
        self._refresh_style(self.camera_state_badge)
        return True

    def apply_snapshot(self, data: bytes, frame_seq: int, capture_ts_ms: int, state: dict) -> bool:
        display = state.get("display", {})
        try:
            expected_seq = int(display.get("frame_seq", -1))
            expected_capture = int(display.get("capture_ts_ms", -1))
        except (TypeError, ValueError):
            return False
        if expected_seq != frame_seq or expected_capture != capture_ts_ms:
            return False
        if not (self._static_visual_mode and self._last_display_frame_seq >= 0):
            if not self.camera_image.set_snapshot(data, display.get("detections", [])):
                return False
        self._last_display_frame_seq = frame_seq
        prefix = "固定画面 · " if self._static_visual_mode else ""
        self.frame_telemetry.setText(f"{prefix}第 {frame_seq:08d} 帧 · 采集 {capture_ts_ms} ms")
        self.camera_state_badge.setText("● 分析完成")
        self.camera_state_badge.setProperty("state", "ok")
        self._refresh_style(self.camera_state_badge)
        self.apply_chain_state(state, force=True)
        return True

    def apply_camera_status(self, event: CameraStatusEvent) -> None:
        color = STATUS_COLORS["low"] if event.valid else STATUS_COLORS["fault"]
        self.camera_stage.set_state(f"{event.width}×{event.height} · {event.fps:.2f} 帧/秒", color)
        self.camera_health.setText(f"采集 · {event.fps:.2f} 帧/秒 · 失败 {event.capture_failures}")
        self.device_log.appendPlainText(f"相机：累计 {event.frames_ok} 帧，{event.fps:.2f} 帧/秒，失败 {event.capture_failures} 次")
        self._mark_sensor_received("ov5640", event.ts_ms)
        self._record_trend("upload_fps", event.ts_ms, event.fps)

    def apply_motion(self, event: MotionEvent) -> None:
        self._mark_sensor_received("mpu6050", event.ts_ms)
        if event.accel_norm_g is None:
            self._queue_mapping_value(self.realtime_panel, "mpu6050", "旧协议数据\n未提供姿态与冲击", source="motion", immediate=True, tone="attention")
            return
        self._queue_mapping_value(self.realtime_panel, "mpu6050", f"{event.accel_norm_g:.2f} g · {event.tilt_deg or 0.0:.1f}°\n{'检测到冲击' if event.impact else '姿态正常'}", source="motion", tone="high" if event.impact else "ok")
        self._record_trend("acceleration", event.ts_ms, event.accel_norm_g)
        if event.tilt_deg is not None:
            self._record_trend("tilt", event.ts_ms, event.tilt_deg)

    def apply_pressure(self, sample: PressureSample) -> None:
        self._last_pressure_sample = sample
        self._mark_sensor_received("pressure", sample.ts_ms)
        self.refresh_sensor_freshness()
        self._record_trend("pressure_kpa", sample.ts_ms, sample.filtered_kpa)

    def apply_voice_status(self, event: VoiceStatusEvent) -> None:
        labels = {"ready": "就绪", "playing": "播放中", "finished": "播放完成", "error": "错误", "initializing": "初始化"}
        state = labels.get(event.state, "未知")
        detail = state
        if event.track:
            detail += f" · 曲目 {event.track}"
        if event.error:
            detail += f"\n{event.error}"
        self._queue_mapping_value(self.realtime_panel, "dfplayer", detail, source="voice_status", immediate=bool(event.error), tone="fault" if event.error else "ok")
        self._queue_mapping_value(self.decision_panel, "dfplayer", f"DFPlayer {detail}", source="voice_status", immediate=bool(event.error), tone="fault" if event.error else "ok")

    def apply_action_status(self, event: ActionStatusEvent) -> None:
        self.protocol_log.appendPlainText(
            f"动作状态：第 {event.frame_seq} 帧，{_state_label(event.action_state)}，{_rgb_pattern_label(event.rgb_pattern)}，"
            f"结果{'已失效' if event.stale else '有效'}"
        )
        if self._last_display_frame_seq >= 0 and event.frame_seq != self._last_display_frame_seq:
            self.protocol_log.appendPlainText(f"已忽略非当前展示帧动作：展示第 {self._last_display_frame_seq} 帧，收到第 {event.frame_seq} 帧")

    def apply_pneumatic_status(self, event: PneumaticStatusEvent) -> None:
        self.pneumatic_panel.apply_status(event)
        self._pneumatic_fault = event.fault
        readiness = protection_readiness(event, require_vision=False)
        pneumatic_failed = event.self_test_failed
        self._queue_mapping_value(self.realtime_panel, "pneumatic",
            f"泵{'开' if event.pump_on else '关'} · 阀{'通电' if event.valve_on else '断电'}\n"
            f"{event.pressure_kpa:.1f} kPa · {'有效' if event.pressure_valid else '无效'}",
            source="pneumatic_status",
            immediate=pneumatic_failed or not event.pressure_valid,
            tone="fault" if pneumatic_failed or not event.pressure_valid else "ok",
        )
        if event.fault != "none":
            self._queue_mapping_value(
                self.peripheral_panel, "pneumatic",
                f"气动故障：{event.fault}",
                source="pneumatic_status", immediate=True, tone="fault",
            )
        feedback = (
            "气动自检失败：泵已输出但压力未上升\n自动充气已锁止，请检查供电、触发电平和阀气路"
            if pneumatic_failed
            else f"真实反馈：泵{'开' if event.pump_on else '关'} · 阀{'通电' if event.valve_on else '断电'}\n"
                 f"状态 {event.state} · 故障 {event.fault}"
        )
        self._queue_mapping_value(
            self.decision_panel, "pneumatic",
            feedback,
            source="pneumatic_status", immediate=pneumatic_failed or event.fault != "none",
            tone="fault" if pneumatic_failed or event.fault != "none" else "ok",
        )
        if pneumatic_failed:
            self._queue_mapping_value(
                self.decision_panel, "mpu6050",
                "充气请求已触发，但气动自检失败\n自动充气已锁止",
                source="pneumatic_status", immediate=True, tone="fault",
            )
        self._queue_mapping_value(self.decision_panel, "pressure",
            f"{'允许' if readiness.allowed else '禁止'}：{readiness.reason}",
            source="pneumatic_status",
            immediate=not readiness.allowed,
            tone="ok" if readiness.allowed else "fault",
        )

    def apply_hardware_health(self, event: HardwareHealthEvent) -> None:
        labels = {
            "healthy": "正常", "degraded": "降级", "fault": "故障", "stale": "过期",
            "disabled": "关闭", "pending": "待自检", "initializing": "初始化",
        }
        for key in ("ov5640", "mpu6050", "pressure", "dfplayer", "rgb"):
            state = event.modules[key]
            self._queue_mapping_value(self.peripheral_panel, key, labels[state], source="hardware_health", immediate=state in {"fault", "stale"}, tone="fault" if state in {"fault", "stale"} else "ok")
        if self._pneumatic_fault != "none":
            pneumatic_text = f"气动故障：{self._pneumatic_fault}"
            pneumatic_tone = "fault"
            pneumatic_immediate = True
        else:
            pneumatic_text = f"泵 {labels[event.modules['pump']]} · 阀 {labels[event.modules['valve']]}"
            pneumatic_tone = "ok" if event.automatic_ready else "fault"
            pneumatic_immediate = not event.automatic_ready
        self._queue_mapping_value(
            self.peripheral_panel, "pneumatic", pneumatic_text,
            source="hardware_health", immediate=pneumatic_immediate, tone=pneumatic_tone,
        )
        self.protocol_log.appendPlainText(
            f"硬件健康：{labels[event.overall]} · 自动{'允许' if event.automatic_ready else '禁止'} · {event.reason}"
        )

    def apply_health(self, health: dict) -> None:
        # /healthz is only a bootstrap source. Once the richer chain state has
        # arrived, letting periodic health polls write these widgets causes the
        # risk/model cards to alternate between real results and placeholders.
        if self._last_state:
            return
        model_state = str(health.get("model_state") or "loading")
        gpu = "CUDA GPU" if str(health.get("gpu") or health.get("device") or "cuda").lower() == "cuda" else "CPU"
        name = str(health.get("model") or "DA3 / YOLO")
        self.model_value.setText(f"{gpu} · {_state_label(model_state)}")
        self.decision_model.setText(f"{name} · {_state_label(model_state)}")
        color = STATUS_COLORS["low"] if model_state == "ready" else STATUS_COLORS["fault"] if model_state == "error" else STATUS_COLORS["loading"]
        self.model_stage.set_state(f"{_state_label(model_state)} · {gpu}", color)
        if model_state == "ready":
            self._set_system_status("等待首帧", "loading")
            self.risk_band.setText("等待视觉帧")
            self.risk_reason.setText("视觉模型已就绪，等待视觉帧与头盔画面匹配。")
        elif model_state == "error":
            self._set_system_status("模型异常", "fault")
            self.risk_band.setText("模型错误")
            self.risk_reason.setText(str(health.get("model_error") or "视觉模型加载失败。"))
        else:
            self._set_system_status("模型加载中", "loading")
            self.risk_reason.setText("画面接收服务已启动，视觉模型正在后台加载。")

    def apply_chain_state(self, state: dict, *, force: bool = False) -> None:
        revision = state.get("revision")
        if not force and isinstance(revision, int) and revision == self._last_state_revision:
            return
        if isinstance(revision, int):
            self._last_state_revision = revision
        self._last_state = state
        upload = state.get("upload", {})
        model = state.get("model", {})
        callback = state.get("callback", {})
        risk = state.get("risk", {})
        action = state.get("action", {})
        display = state.get("display", {})
        if display.get("ready"):
            try:
                self._last_display_frame_seq = int(display.get("frame_seq", -1))
            except (TypeError, ValueError):
                pass
        model_state = str(model.get("state", "loading"))
        is_stale = bool(action.get("stale", False)) or action.get("state") == "fault"
        band = "fault" if is_stale else str(risk.get("band", "loading"))
        score = int(risk.get("score", 0)) if risk.get("valid") and not is_stale else None
        band_labels = {"loading": "等待模型", "low": "低风险", "attention": "需要注意", "high": "高风险", "critical": "严重风险", "fault": "结果失效"}
        action_labels = {"loading": "等待策略", "safe": "安全提示", "attention": "注意提示", "high": "高风险提示", "critical": "严重提示", "fault": "禁止执行"}
        frame_seq = int(display.get("frame_seq", -1)) if display.get("ready") else int(risk.get("frame_seq", upload.get("last_frame_seq", -1)) or -1)
        age = upload.get("frame_age_ms")
        model_latency = model.get("latency_ms")
        callback_latency = callback.get("latency_ms")
        self.device_value.setText(f"{_device_label(state.get('device_id'))} · {_state_label(upload.get('state'))}")
        self.decision_frame.setText(f"第 {frame_seq:08d} 帧" if frame_seq >= 0 else "等待视觉帧")
        gpu_label = "CUDA GPU" if str(model.get("gpu", "cuda")).lower() == "cuda" else "CPU"
        self.model_value.setText(f"{gpu_label} · {_state_label(model_state)}")
        self.decision_model.setText(
            f"{model.get('name') or 'DA3 / YOLO'} · {_state_label(model_state)} · {float(model_latency):.0f} ms"
            if isinstance(model_latency, (int, float)) else f"{model.get('name') or 'DA3 / YOLO'} · {_state_label(model_state)}"
        )
        self.decision_callback.setText(
            f"本地服务回传 · {_state_label(callback.get('state'))} · {float(callback_latency):.0f} ms"
            if isinstance(callback_latency, (int, float)) else "本地服务回传 · 等待真实反馈"
        )
        self.decision_freshness.setText(
            f"帧时效 {int(age)} ms · {float(upload.get('fps', 0)):.2f} 帧/秒" if isinstance(age, (int, float)) else "等待健康检查"
        )
        self.decision_counts.setText(
            f"接收 {int(upload.get('accepted_frames', 0) or 0)} · 分析 {int(model.get('valid_results', 0) or 0)} · 确认 {int(callback.get('confirmed_count', 0) or 0)}"
        )

        self.upload_stage.set_state(
            f"{float(upload.get('fps', 0)):.2f} 帧/秒 · 第 {int(upload.get('last_frame_seq', -1))} 帧",
            STATUS_COLORS["low"] if upload.get("state") == "healthy" else STATUS_COLORS["fault"],
        )
        self.model_stage.set_state(
            f"{_state_label(model_state)} · {float(model_latency):.0f} 毫秒" if isinstance(model_latency, (int, float)) else _state_label(model_state),
            STATUS_COLORS["low"] if model_state == "ready" else STATUS_COLORS["loading"] if model_state == "loading" else STATUS_COLORS["fault"],
        )
        self.action_stage.set_state(f"{_state_label(callback.get('state'))} · 第 {int(action.get('frame_seq', -1))} 帧", STATUS_COLORS.get(band, STATUS_COLORS["loading"]))

        self.risk_score.setText(f"{score:02d}" if score is not None else "--")
        self.risk_band.setText(band_labels.get(band, "状态未知"))
        self.result_state.setText("● 结果已失效" if is_stale else "● 结果有效" if score is not None else "● 等待模型")
        self.risk_reason.setText(_risk_reason_label(risk.get("reason"), model_state=model_state, stale=is_stale))
        self._queue_mapping_value(self.realtime_panel, "ov5640",
            f"{risk.get('dominant_class') or '目标未知'}\n风险 {score if score is not None else '—'} / 100",
            source="chain_state",
            immediate=is_stale,
            tone="fault" if is_stale else str(band) if band in {"low", "attention", "high", "critical"} else "info",
        )
        self._queue_mapping_value(self.decision_panel, "ov5640",
            f"{band_labels.get(band, '状态未知')} · {score if score is not None else '—'} / 100\n"
            f"{'真实确认' if action.get('confirmed') else '等待反馈'}",
            source="chain_state",
            immediate=is_stale or band in {"high", "critical"},
            tone="fault" if is_stale else str(band) if band in {"low", "attention", "high", "critical"} else "info",
        )
        if score is not None and score >= 80:
            self._queue_mapping_value(self.decision_panel, "mpu6050", "严重风险达到气动策略阈值\n等待 ESP32 泵阀真实反馈", source="chain_state", immediate=True, tone="critical")
        elif score is not None and score >= 60:
            self._queue_mapping_value(self.decision_panel, "mpu6050", "高风险达到气动策略阈值\n等待 ESP32 泵阀真实反馈", source="chain_state", immediate=True, tone="high")
        else:
            self._queue_mapping_value(self.decision_panel, "mpu6050", "未达到气动策略阈值\n以 ESP32 泵阀真实反馈为准", source="chain_state", tone="ok")
        rgb_pattern = str(action.get("rgb_pattern") or "")
        rgb_confirmed = bool(action.get("confirmed")) and bool(rgb_pattern)
        self._queue_mapping_value(
            self.realtime_panel, "rgb",
            f"{_rgb_pattern_label(rgb_pattern)}\nESP32 动作已确认" if rgb_confirmed else "等待 ESP32 动作反馈\n灯光模式未确认",
            source="chain_state", immediate=rgb_confirmed, tone="info",
        )
        self._queue_mapping_value(
            self.decision_panel, "rgb",
            f"{_rgb_pattern_label(rgb_pattern)}\n第 {action.get('frame_seq')} 帧真实反馈" if rgb_confirmed else "等待 ESP32 反馈\n灯光模式未确认",
            source="chain_state", immediate=rgb_confirmed, tone="info",
        )
        self.action_name.setText(action_labels.get(str(action.get("state", "loading")), "状态未知"))
        if action.get("confirmed"):
            ack_text = f"动作已确认 · 第 {int(action.get('frame_seq', -1))} 帧"
            e2e = action.get("e2e_latency_ms")
            if isinstance(e2e, (int, float)) and e2e >= 0:
                ack_text += f" · 端到端 {int(round(float(e2e)))} 毫秒"
            self.action_ack.setText(ack_text)
        else:
            self.action_ack.setText("等待动作确认")
        self.execution_guard.setText(
            "旧数据、断链或无效数据：不生成新的执行结论。" if is_stale or not risk.get("valid")
            else "数据新鲜且有效：显示策略建议；真实执行仅以 ESP32 串口反馈为准。"
        )
        risk_frame_seq = int(risk.get("frame_seq", -1) or -1)
        if score is not None and risk_frame_seq >= 0 and risk_frame_seq != self._last_trend_frame:
            self._last_trend_frame = risk_frame_seq
            self.risk_trend.add_score(score)
            self._record_trend("risk_score", QtCore.QDateTime.currentMSecsSinceEpoch(), score, band_labels.get(band, ""))
        self.camera_uplink.setText(f"上传 · {float(upload.get('fps', 0)):.2f} 帧/秒 · 第 {frame_seq} 帧" if frame_seq >= 0 else "上传 · 等待首帧")
        if is_stale:
            self._set_system_status("闭环异常", "fault")
        elif model_state == "loading":
            self._set_system_status("模型加载中", "loading")
        elif upload.get("state") == "healthy" and callback.get("state") == "confirmed" and action.get("confirmed"):
            self._set_system_status("闭环运行正常", band if band in STATUS_COLORS else "low")
        else:
            self._set_system_status("链路连接中", "loading")
        self.chain_log.appendPlainText(
            f"第 {upload.get('last_frame_seq')} 帧：上传{_state_label(upload.get('state'))}，模型{_state_label(model_state)}，"
            f"回传{_state_label(callback.get('state'))}，动作{_state_label(action.get('state'))}"
        )
        self.last_error_text = _error_label(state.get("last_error"))

    def _mark_sensor_received(self, key: str, source_ts_ms: int) -> None:
        self._sensor_received_at_ms[key] = QtCore.QDateTime.currentMSecsSinceEpoch()
        self._sensor_source_ts_ms[key] = source_ts_ms

    def refresh_sensor_freshness(self) -> None:
        sample = self._last_pressure_sample
        received = self._sensor_received_at_ms.get("pressure")
        if sample is None or received is None:
            return
        self._queue_mapping_value(
            self.realtime_panel, "pressure",
            f"{sample.filtered_kpa:.2f} kPa\n{'有效' if sample.valid else '无效'}",
            source="pressure",
            immediate=not sample.valid,
            tone="ok" if sample.valid else "fault",
        )

    def set_session_path(self, path: str) -> None:
        self.session_log.setPlainText(path)

    @staticmethod
    def _refresh_style(widget: QtWidgets.QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)
