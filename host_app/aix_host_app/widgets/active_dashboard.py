from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..models import ActionStatusEvent, CameraStatusEvent, MotionEvent, PneumaticStatusEvent, PressureSample, VoiceStatusEvent
from .pneumatic_calibration_panel import PneumaticCalibrationPanel
from .vision_canvas import VisionCanvas


STATUS_COLORS = {
    "loading": "#38BDF8",
    "low": "#34D399",
    "attention": "#FBBF24",
    "high": "#FB923C",
    "critical": "#F87171",
    "fault": "#C084FC",
}

STATUS_SURFACES = {
    "loading": "#0B2940",
    "low": "#0D3029",
    "attention": "#3A2C0A",
    "high": "#3B200D",
    "critical": "#3B171C",
    "fault": "#2C193C",
}

STATE_LABELS = {
    "loading": "加载中",
    "ready": "已就绪",
    "healthy": "正常",
    "waiting": "等待中",
    "confirmed": "已确认",
    "failed": "失败",
    "error": "异常",
    "streaming": "采集中",
    "safe": "安全",
    "attention": "注意",
    "high": "高风险",
    "critical": "严重风险",
    "fault": "故障",
}

RISK_REASON_LABELS = {
    "scene_proximity": "前向场景接近程度升高，系统已根据相对深度生成本帧风险判断。",
    "object_proximity": "前向目标接近程度升高，系统已根据目标与相对深度生成本帧风险判断。",
}

RGB_PATTERN_LABELS = {
    "blue_blink_1hz": "蓝灯慢闪",
    "green_solid": "绿灯常亮",
    "yellow_blink_1hz": "黄灯慢闪",
    "orange_blink_2hz": "橙灯快速闪烁",
    "red_double_pulse": "红灯双脉冲",
    "purple_blink_1hz": "紫灯慢闪",
}


def _state_label(value: object) -> str:
    text = str(value or "waiting")
    return STATE_LABELS.get(text, "状态未知")


def _risk_reason_label(value: object, *, model_state: str, stale: bool) -> str:
    if stale:
        return "超过 3 秒未收到新鲜合法结果，旧风险已隔离，系统等待链路自动恢复。"
    text = str(value or "")
    if text in RISK_REASON_LABELS:
        return RISK_REASON_LABELS[text]
    if model_state == "loading":
        return "视觉模型正在后台加载，上传帧会自动保留最新一张。"
    if not text:
        return "等待视觉模型给出本帧风险判断。"
    return "已生成本帧视觉风险判断，详细原因可在诊断页查看。"


def _rgb_pattern_label(value: object) -> str:
    return RGB_PATTERN_LABELS.get(str(value or ""), "灯光状态未知")


def _error_label(value: object) -> str:
    text = str(value or "")
    if not text:
        return "无"
    if "PC service unavailable" in text:
        return "PC 服务超过 3 秒无响应"
    if "callback" in text.lower():
        return "风险结果回传失败"
    return "存在异常，请查看诊断信息"


def _device_label(value: object) -> str:
    raw = str(value or "")
    suffix = raw.rsplit("-", 1)[-1]
    if suffix.isdigit():
        return f"头盔设备 {suffix.zfill(2)}"
    return "头盔设备"


class _RiskTrend(QtWidgets.QWidget):
    """Small, dependency-free risk history chart for the operator view."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.samples: list[int] = []
        self.setObjectName("riskTrend")
        self.setMinimumHeight(76)
        self.setAccessibleName("最近视觉风险趋势")

    def add_score(self, score: int) -> None:
        self.samples.append(max(0, min(100, int(score))))
        self.samples = self.samples[-48:]
        self.setAccessibleDescription(
            f"最近 {len(self.samples)} 个结果，当前风险 {self.samples[-1]} 分"
        )
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(8, 7, -8, -8)
        if rect.width() <= 1 or rect.height() <= 1:
            return
        painter.setPen(QtGui.QPen(QtGui.QColor("#26354A"), 1))
        for level in (30, 60, 80):
            y = rect.bottom() - (level / 100.0) * rect.height()
            painter.drawLine(rect.left(), int(y), rect.right(), int(y))
        if not self.samples:
            painter.setPen(QtGui.QColor("#718096"))
            painter.drawText(rect, QtCore.Qt.AlignmentFlag.AlignCenter, "等待有效风险结果")
            return
        count = len(self.samples)
        points: list[QtCore.QPointF] = []
        for index, score in enumerate(self.samples):
            x = rect.left() if count == 1 else rect.left() + index * rect.width() / (count - 1)
            y = rect.bottom() - score * rect.height() / 100.0
            points.append(QtCore.QPointF(x, y))
        path = QtGui.QPainterPath(points[0])
        for point in points[1:]:
            path.lineTo(point)
        fill_path = QtGui.QPainterPath(path)
        fill_path.lineTo(points[-1].x(), rect.bottom())
        fill_path.lineTo(points[0].x(), rect.bottom())
        fill_path.closeSubpath()
        fill = QtGui.QColor("#38BDF8")
        fill.setAlpha(32)
        painter.fillPath(fill_path, fill)
        painter.setPen(QtGui.QPen(QtGui.QColor("#38BDF8"), 2))
        painter.drawPath(path)
        painter.setBrush(QtGui.QColor("#E6F6FF"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#07111F"), 2))
        painter.drawEllipse(points[-1], 4, 4)


class _Stage(QtWidgets.QFrame):
    def __init__(self, index: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("chainStage")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        heading = QtWidgets.QHBoxLayout()
        number = QtWidgets.QLabel(index)
        number.setObjectName("stageIndex")
        self.dot = QtWidgets.QLabel("●")
        self.dot.setObjectName("stageDot")
        self.title = QtWidgets.QLabel(title)
        self.title.setObjectName("stageTitle")
        heading.addWidget(number)
        heading.addWidget(self.dot)
        heading.addWidget(self.title, 1)
        self.meta = QtWidgets.QLabel("等待状态")
        self.meta.setObjectName("monoMuted")
        layout.addLayout(heading)
        layout.addWidget(self.meta)

    def set_state(self, meta: str, color: str) -> None:
        self.meta.setText(meta)
        self.dot.setStyleSheet(f"color: {color}; background: transparent;")


class _Metric(QtWidgets.QFrame):
    def __init__(self, title: str, value: str = "—", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("bottomMetric")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(3)
        label = QtWidgets.QLabel(title)
        label.setObjectName("metricTitle")
        self.value = QtWidgets.QLabel(value)
        self.value.setObjectName("metricMono")
        layout.addWidget(label)
        layout.addWidget(self.value)


class _StatusColumn(QtWidgets.QFrame):
    """Narrow column whose rows stay horizontally aligned with the result pane."""

    def __init__(self, object_name: str, title: str, rows: tuple[tuple[str, str], ...], parent=None) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        heading = QtWidgets.QLabel(title)
        heading.setObjectName("panelTitle")
        heading.setWordWrap(True)
        heading.setFixedHeight(26)
        layout.addWidget(heading)
        self.values: dict[str, QtWidgets.QLabel] = {}
        self.rows: dict[str, QtWidgets.QFrame] = {}
        for key, label in rows:
            block = QtWidgets.QFrame()
            block.setObjectName("riskHero")
            block.setFixedHeight(76)
            block_layout = QtWidgets.QVBoxLayout(block)
            block_layout.setContentsMargins(8, 8, 8, 8)
            name = QtWidgets.QLabel(label)
            name.setObjectName("metricTitle")
            value = QtWidgets.QLabel("等待")
            value.setObjectName("metricMono")
            value.setWordWrap(True)
            block_layout.addWidget(name)
            block_layout.addWidget(value)
            layout.addWidget(block)
            self.values[key] = value
            self.rows[key] = block
        layout.addStretch(1)

    def set_value(self, key: str, value: str) -> None:
        self.values[key].setText(value)


class ActiveVisionDashboard(QtWidgets.QWidget):
    settings_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_state: dict = {}
        self._last_trend_frame = -1
        self._last_display_frame_seq = -1
        self._last_state_revision: int | None = None
        self._sensor_received_at_ms: dict[str, int] = {}
        self._sensor_source_ts_ms: dict[str, int] = {}
        self._last_pressure_sample: PressureSample | None = None
        self.setObjectName("activeDashboard")

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(self._build_header())
        root.addWidget(self._build_chain())
        root.addWidget(self._build_workspace(), 1)
        root.addWidget(self._build_metrics())
        self.diagnostics = self._build_diagnostics()
        self.diagnostics.hide()
        root.addWidget(self.diagnostics)
        self._sensor_freshness_timer = QtCore.QTimer(self)
        self._sensor_freshness_timer.setInterval(500)
        self._sensor_freshness_timer.timeout.connect(self.refresh_sensor_freshness)
        self._sensor_freshness_timer.start()

    def _build_header(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("instrumentHeader")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(18, 10, 12, 10)
        title = QtWidgets.QLabel("AIX 主动视觉安全监控台")
        title.setObjectName("instrumentTitle")
        self.instrument_subtitle = QtWidgets.QLabel("主动视觉闭环监控")
        self.instrument_subtitle.setObjectName("instrumentSubtitle")
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(title)
        titles.addWidget(self.instrument_subtitle)
        layout.addLayout(titles, 1)
        self.system_status = QtWidgets.QLabel("● 系统启动中")
        self.system_status.setObjectName("systemStatus")
        self.device_value = QtWidgets.QLabel("头盔设备 · 等待连接")
        self.device_value.setObjectName("headerTelemetry")
        self.model_value = QtWidgets.QLabel("视觉模型 · 加载中")
        self.model_value.setObjectName("headerTelemetry")
        layout.addWidget(self.system_status)
        layout.addWidget(self.device_value)
        layout.addWidget(self.model_value)
        self.display_button = QtWidgets.QPushButton("运行总览")
        self.diagnostic_button = QtWidgets.QPushButton("诊断信息")
        self.settings_button = QtWidgets.QPushButton("系统设置")
        self.display_button.setCheckable(True)
        self.diagnostic_button.setCheckable(True)
        self.display_button.setChecked(True)
        self.display_button.clicked.connect(lambda: self.set_diagnostic_mode(False))
        self.diagnostic_button.clicked.connect(lambda: self.set_diagnostic_mode(True))
        self.settings_button.clicked.connect(self.settings_requested)
        for button in (self.display_button, self.diagnostic_button, self.settings_button):
            button.setObjectName("modeButton")
            layout.addWidget(button)
        return frame

    def _build_chain(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("chainBand")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.camera_stage = _Stage("01", "相机采集")
        self.upload_stage = _Stage("02", "图像上传")
        self.model_stage = _Stage("03", "上位机视觉推理")
        self.action_stage = _Stage("04", "动作反馈")
        for stage in (self.camera_stage, self.upload_stage, self.model_stage, self.action_stage):
            layout.addWidget(stage, 1)
        return frame

    def _build_workspace(self) -> QtWidgets.QWidget:
        workspace = QtWidgets.QWidget()
        workspace.setObjectName("workspaceSplitter")
        layout = QtWidgets.QHBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.workspace_ratios = (6, 1, 1, 2)
        self.sensor_row_keys = ("ov5640", "mpu6050", "pressure")
        camera = QtWidgets.QFrame()
        camera.setObjectName("visionPanel")
        self.camera_panel = camera
        camera_layout = QtWidgets.QVBoxLayout(camera)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        camera_layout.setSpacing(0)
        camera_head = QtWidgets.QFrame()
        camera_head.setObjectName("panelHead")
        head_layout = QtWidgets.QHBoxLayout(camera_head)
        head_layout.setContentsMargins(16, 10, 16, 10)
        camera_title = QtWidgets.QLabel("已分析视觉画面")
        camera_title.setObjectName("panelTitle")
        self.camera_state_badge = QtWidgets.QLabel("● 等待画面")
        self.camera_state_badge.setObjectName("softBadge")
        head_layout.addWidget(camera_title)
        head_layout.addWidget(self.camera_state_badge)
        self.frame_telemetry = QtWidgets.QLabel("等待上位机已分析帧")
        self.frame_telemetry.setObjectName("monoMuted")
        head_layout.addWidget(self.frame_telemetry, 1, QtCore.Qt.AlignmentFlag.AlignRight)
        self.camera_image = VisionCanvas()
        camera_footer = QtWidgets.QFrame()
        camera_footer.setObjectName("cameraFooter")
        footer_layout = QtWidgets.QHBoxLayout(camera_footer)
        footer_layout.setContentsMargins(16, 7, 16, 7)
        footer_layout.setSpacing(20)
        self.camera_source = QtWidgets.QLabel("图像来源 · 头盔相机")
        self.camera_health = QtWidgets.QLabel("采集状态 · 等待连接")
        self.camera_uplink = QtWidgets.QLabel("传输状态 · 等待首帧")
        for label in (self.camera_source, self.camera_health, self.camera_uplink):
            label.setObjectName("cameraTelemetry")
            footer_layout.addWidget(label)
        footer_layout.addStretch(1)
        camera_layout.addWidget(camera_head)
        camera_layout.addWidget(self.camera_image, 1)
        camera_layout.addWidget(camera_footer)

        decision = QtWidgets.QFrame()
        decision.setObjectName("decisionPanel")
        decision.setMinimumWidth(0)
        decision.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Expanding)
        self.decision_panel = decision
        decision_layout = QtWidgets.QVBoxLayout(decision)
        decision_layout.setContentsMargins(16, 14, 16, 14)
        decision_layout.setSpacing(10)
        decision_head = QtWidgets.QHBoxLayout()
        heading = QtWidgets.QLabel("本帧视觉判定")
        heading.setObjectName("panelTitle")
        self.result_state = QtWidgets.QLabel("● 等待模型")
        self.result_state.setObjectName("softBadge")
        self.result_state.setFixedHeight(26)
        decision_head.addWidget(heading)
        decision_head.addStretch(1)
        decision_head.addWidget(self.result_state)
        decision_head_widget = QtWidgets.QWidget()
        decision_head_widget.setLayout(decision_head)
        decision_head_widget.setFixedHeight(26)
        decision_layout.addWidget(decision_head_widget)

        self.derived_values: dict[str, QtWidgets.QLabel] = {}
        self.derived_rows: dict[str, QtWidgets.QFrame] = {}
        self.derived_row_layouts: dict[str, QtWidgets.QVBoxLayout] = {}
        for key, label in (("ov5640", "风险 / 帧"), ("mpu6050", "RGB / 语音"), ("pressure", "气动总成")):
            row = QtWidgets.QFrame()
            row.setObjectName("riskHero")
            row.setFixedHeight(76)
            row_layout = QtWidgets.QVBoxLayout(row)
            row_layout.setContentsMargins(7, 5, 7, 5)
            row_layout.setSpacing(1)
            value = QtWidgets.QLabel("等待")
            value.setObjectName("metricMono")
            value.setMaximumHeight(18)
            row_layout.addWidget(value)
            decision_layout.addWidget(row)
            self.derived_values[key] = value
            self.derived_rows[key] = row
            self.derived_row_layouts[key] = row_layout
        decision_layout.addStretch(1)

        risk_hero = QtWidgets.QFrame()
        self.risk_hero = risk_hero
        risk_hero.setObjectName("riskHero")
        risk_hero_layout = QtWidgets.QVBoxLayout(risk_hero)
        risk_hero_layout.setContentsMargins(16, 13, 16, 13)
        risk_hero_layout.setSpacing(8)
        risk_value_row = QtWidgets.QHBoxLayout()
        risk_value_row.setSpacing(14)
        self.risk_score = QtWidgets.QLabel("--")
        self.risk_score.setObjectName("riskScore")
        self.risk_band = QtWidgets.QLabel("模型加载中")
        self.risk_band.setObjectName("riskBand")
        risk_side = QtWidgets.QVBoxLayout()
        risk_side.setSpacing(4)
        risk_caption = QtWidgets.QLabel("相对风险 · 满分 100")
        risk_caption.setObjectName("monoMuted")
        risk_side.addWidget(self.risk_band)
        risk_side.addWidget(risk_caption)
        risk_value_row.addWidget(self.risk_score)
        risk_value_row.addLayout(risk_side, 1)
        risk_hero_layout.addLayout(risk_value_row)
        self.risk_gauge = QtWidgets.QProgressBar()
        self.risk_gauge.setObjectName("riskGauge")
        self.risk_gauge.setRange(0, 100)
        self.risk_gauge.setValue(0)
        self.risk_gauge.setTextVisible(False)
        risk_hero_layout.addWidget(self.risk_gauge)
        self.risk_scale = QtWidgets.QFrame()
        self.risk_scale.setObjectName("transparentFrame")
        scale = QtWidgets.QHBoxLayout(self.risk_scale)
        scale.setContentsMargins(0, 0, 0, 0)
        scale.setSpacing(0)
        for text in ("低风险 0–29", "注意 30–59", "高风险 60–79", "严重 80–100"):
            label = QtWidgets.QLabel(text)
            label.setObjectName("scaleLabel")
            scale.addWidget(label, 1)
        risk_hero_layout.addWidget(self.risk_scale)
        self.risk_reason = QtWidgets.QLabel("画面接收服务启动后，视觉模型会在后台加载。")
        self.risk_reason.setObjectName("muted")
        self.risk_reason.setWordWrap(True)
        risk_hero_layout.addWidget(self.risk_reason)

        action_hero = QtWidgets.QFrame()
        self.action_hero = action_hero
        action_hero.setObjectName("actionHero")
        action_hero_layout = QtWidgets.QHBoxLayout(action_hero)
        action_hero_layout.setContentsMargins(14, 11, 14, 11)
        action_hero_layout.setSpacing(12)
        self.action_indicator = QtWidgets.QFrame()
        self.action_indicator.setObjectName("actionIndicator")
        self.action_indicator.setFixedWidth(5)
        action_hero_layout.addWidget(self.action_indicator)
        action_text = QtWidgets.QVBoxLayout()
        action_text.setSpacing(4)
        self.action_name = QtWidgets.QLabel("启动提示")
        self.action_name.setObjectName("actionName")
        self.action_pattern = QtWidgets.QLabel("板载指示灯 · 蓝灯慢闪 · 亮度 20%")
        self.action_pattern.setObjectName("metricMono")
        self.action_ack = QtWidgets.QLabel("等待动作确认")
        self.action_ack.setObjectName("monoMuted")
        self.pneumatic_summary = QtWidgets.QLabel("气动执行器 · 未从设备读取")
        self.pneumatic_summary.setObjectName("monoMuted")
        action_text.addWidget(self.action_name)
        action_text.addWidget(self.action_pattern)
        action_text.addWidget(self.action_ack)
        action_text.addWidget(self.pneumatic_summary)
        action_hero_layout.addLayout(action_text, 1)
        decision_layout.addWidget(risk_hero)
        decision_layout.addWidget(action_hero)

        self.telemetry_heading = QtWidgets.QLabel("闭环执行摘要")
        self.telemetry_heading.setObjectName("sectionTitle")
        decision_layout.addWidget(self.telemetry_heading)
        telemetry = QtWidgets.QFrame()
        self.telemetry_panel = telemetry
        telemetry.setObjectName("decisionTelemetry")
        telemetry_layout = QtWidgets.QGridLayout(telemetry)
        telemetry_layout.setContentsMargins(12, 8, 12, 8)
        telemetry_layout.setHorizontalSpacing(12)
        telemetry_layout.setVerticalSpacing(7)
        rows = (
            ("来源帧", "decision_frame", "等待视觉帧"),
            ("视觉模型", "decision_model", "加载中"),
            ("结果回传", "decision_callback", "等待中"),
            ("数据时效", "decision_freshness", "— 毫秒 · 0.00 帧/秒"),
            ("累计处理", "decision_counts", "接收 0 · 分析 0 · 确认 0"),
        )
        for row, (title, attribute, initial) in enumerate(rows):
            title_label = QtWidgets.QLabel(title)
            title_label.setObjectName("telemetryKey")
            value_label = QtWidgets.QLabel(initial)
            value_label.setObjectName("telemetryValue")
            value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
            setattr(self, f"{attribute}_key", title_label)
            setattr(self, attribute, value_label)
            telemetry_layout.addWidget(title_label, row, 0)
            telemetry_layout.addWidget(value_label, row, 1)
        telemetry_layout.setColumnStretch(1, 1)
        decision_layout.addWidget(telemetry)

        self.trend_header = QtWidgets.QFrame()
        self.trend_header.setObjectName("transparentFrame")
        trend_head = QtWidgets.QHBoxLayout(self.trend_header)
        trend_head.setContentsMargins(0, 0, 0, 0)
        trend_title = QtWidgets.QLabel("最近风险趋势")
        trend_title.setObjectName("sectionTitle")
        trend_note = QtWidgets.QLabel("最近 48 个有效结果")
        trend_note.setObjectName("monoMuted")
        trend_head.addWidget(trend_title)
        trend_head.addStretch(1)
        trend_head.addWidget(trend_note)
        decision_layout.addWidget(self.trend_header)
        self.risk_trend = _RiskTrend()
        self.risk_trend.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        decision_layout.addWidget(self.risk_trend)

        self.safety_note = QtWidgets.QLabel("说明：风险分数表示相对视觉接近程度，不等同于碰撞概率或安全执行器结论。")
        self.safety_note.setObjectName("safetyNote")
        self.safety_note.setWordWrap(True)
        decision_layout.addWidget(self.safety_note)

        self.peripheral_panel = _StatusColumn(
            "peripheralPanel", "感知外设",
            (("ov5640", "OV5640"), ("mpu6050", "MPU6050"), ("pressure", "压力传感器")),
        )
        self.realtime_panel = _StatusColumn(
            "realtimePanel", "实时数据",
            (("ov5640", "目标 / 风险"), ("mpu6050", "加速度 / 倾角"), ("pressure", "压力 / 时效")),
        )
        self.peripheral_values = self.peripheral_panel.values
        self.realtime_values = self.realtime_panel.values
        self.peripheral_panel.set_value("ov5640", "离线\n采样率 — · 更新 —")
        self.peripheral_panel.set_value("mpu6050", "离线\n采样率 — · 更新 —")
        self.peripheral_panel.set_value("pressure", "离线\n采样率 — · 更新 —")
        self.realtime_panel.set_value("ov5640", "等待有效帧")
        self.realtime_panel.set_value("mpu6050", "等待数据")
        self.realtime_panel.set_value("pressure", "等待数据")
        self.execution_guard = QtWidgets.QLabel("旧/无效数据不生成新执行结论")
        self.execution_guard.setObjectName("safetyNote")
        self.execution_guard.setWordWrap(True)
        self.pneumatic_acceptance_note = QtWidgets.QLabel("策略与真实执行分开；尚未完成气囊实物验收")
        self.pneumatic_acceptance_note.setObjectName("safetyNote")
        self.pneumatic_acceptance_note.setWordWrap(True)
        self.voice_status_value = QtWidgets.QLabel("DFPlayer · 等待状态")
        self.voice_status_value.setObjectName("monoMuted")
        for label in (self.action_pattern, self.action_ack):
            label.setMaximumHeight(18)
            label.setWordWrap(False)
            self.derived_row_layouts["ov5640"].addWidget(label)
        for label in (self.voice_status_value, self.execution_guard):
            label.setMaximumHeight(18)
            label.setWordWrap(False)
            self.derived_row_layouts["mpu6050"].addWidget(label)
        for label in (self.pneumatic_summary, self.pneumatic_acceptance_note):
            label.setMaximumHeight(18)
            label.setWordWrap(False)
            self.derived_row_layouts["pressure"].addWidget(label)
        # The three mapped rows are the primary compact control-center surface.
        # Legacy detailed cards remain state holders for diagnostics, but do not
        # consume vertical space and break cross-column row alignment.
        for legacy in (self.risk_hero, self.action_hero, self.telemetry_heading, self.telemetry_panel):
            legacy.hide()
        for widget in (camera, self.peripheral_panel, self.realtime_panel):
            widget.setMinimumWidth(0)
            widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Ignored, QtWidgets.QSizePolicy.Policy.Expanding)
        layout.addWidget(camera, self.workspace_ratios[0])
        layout.addWidget(self.peripheral_panel, self.workspace_ratios[1])
        layout.addWidget(self.realtime_panel, self.workspace_ratios[2])
        layout.addWidget(decision, self.workspace_ratios[3])
        return workspace

    def _build_metrics(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("metricBand")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.upload_fps = _Metric("上传帧率")
        self.frame_age = _Metric("帧时效")
        self.infer_latency = _Metric("推理耗时")
        self.callback_latency = _Metric("回传耗时")
        self.action_frame = _Metric("动作确认帧")
        self.last_error = _Metric("最后错误")
        for metric in (self.upload_fps, self.frame_age, self.infer_latency, self.callback_latency, self.action_frame, self.last_error):
            layout.addWidget(metric, 1)
        return frame

    def _build_diagnostics(self) -> QtWidgets.QTabWidget:
        tabs = QtWidgets.QTabWidget()
        tabs.setObjectName("diagnostics")
        self.chain_log = QtWidgets.QPlainTextEdit()
        self.protocol_log = QtWidgets.QPlainTextEdit()
        self.device_log = QtWidgets.QPlainTextEdit("压力传感器：等待串口\nMPU6050：等待串口\n气动模块：未从设备读取")
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
        tabs.setMaximumHeight(220)
        return tabs

    def set_diagnostic_mode(self, enabled: bool) -> None:
        self.diagnostics.setVisible(enabled)
        self.display_button.setChecked(not enabled)
        self.diagnostic_button.setChecked(enabled)

    def _apply_risk_tint(self, band: str) -> None:
        color = STATUS_COLORS.get(band, STATUS_COLORS["loading"])
        surface = STATUS_SURFACES.get(band, STATUS_SURFACES["loading"])
        self.risk_score.setStyleSheet(f"color: {color}; background: transparent;")
        self.risk_band.setStyleSheet(f"color: {color}; background: transparent;")
        self.result_state.setStyleSheet(
            f"color: {color}; background: {surface}; border: 1px solid {color};"
            "border-radius: 10px; padding: 3px 9px;"
        )
        self.action_indicator.setStyleSheet(
            f"background: {color}; border: none; border-radius: 2px;"
        )
        self.risk_gauge.setStyleSheet(
            "QProgressBar { background: #1A2638; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 3px; }}"
        )

    def _set_system_status(self, text: str, band: str) -> None:
        color = STATUS_COLORS.get(band, STATUS_COLORS["loading"])
        surface = STATUS_SURFACES.get(band, STATUS_SURFACES["loading"])
        self.system_status.setText(f"● {text}")
        self.system_status.setStyleSheet(
            f"color: {color}; background: {surface}; border: 1px solid {color};"
            "border-radius: 11px; padding: 4px 10px; font-weight: 650;"
        )

    def apply_frame(self, data: bytes, frame_seq: int, capture_ts_ms: int) -> bool:
        if not self.camera_image.set_snapshot(data, []):
            return False
        self._last_display_frame_seq = frame_seq
        self.frame_telemetry.setText(f"第 {frame_seq:08d} 帧 · 采集时间 {capture_ts_ms} 毫秒")
        self.camera_state_badge.setText("● 已完成分析")
        self.camera_state_badge.setStyleSheet(
            "color: #34D399; background: #0D3029; border: 1px solid #34D399;"
            "border-radius: 10px; padding: 3px 9px;"
        )
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
        if not self.camera_image.set_snapshot(data, display.get("detections", [])):
            return False
        self._last_display_frame_seq = frame_seq
        self.frame_telemetry.setText(f"第 {frame_seq:08d} 帧 · 采集时间 {capture_ts_ms} 毫秒")
        self.camera_state_badge.setText("● 已完成分析")
        self.camera_state_badge.setStyleSheet(
            "color: #34D399; background: #0D3029; border: 1px solid #34D399;"
            "border-radius: 10px; padding: 3px 9px;"
        )
        self.apply_chain_state(state, force=True)
        return True

    def set_compact_mode(self, compact: bool) -> None:
        self.trend_header.setVisible(not compact)
        self.risk_trend.setVisible(not compact)
        self.safety_note.setVisible(not compact)

    def workspace_column_widths(self) -> tuple[int, int, int, int]:
        """Actual rendered widths, used to guard the 6:1:1:2 operator mapping."""
        return (
            self.camera_panel.width(),
            self.peripheral_panel.width(), self.realtime_panel.width(), self.decision_panel.width(),
        )

    def sensor_mapping_row_geometries(self) -> tuple[tuple[QtCore.QRect, QtCore.QRect, QtCore.QRect], ...]:
        def in_workspace(widget: QtWidgets.QWidget) -> QtCore.QRect:
            point = widget.mapTo(self, QtCore.QPoint(0, 0))
            return QtCore.QRect(point, widget.size())
        return tuple(
            (in_workspace(self.peripheral_panel.rows[key]), in_workspace(self.realtime_panel.rows[key]), in_workspace(self.derived_rows[key]))
            for key in self.sensor_row_keys
        )

    def apply_camera_status(self, event: CameraStatusEvent) -> None:
        color = STATUS_COLORS["low"] if event.valid else STATUS_COLORS["fault"]
        self.camera_stage.set_state(f"{event.width}×{event.height} · {event.fps:.2f} 帧/秒", color)
        self.camera_health.setText(
            f"采集状态 · {event.fps:.2f} 帧/秒 · 失败 {event.capture_failures} 次"
        )
        self.device_log.appendPlainText(
            f"相机：累计 {event.frames_ok} 帧，{event.fps:.2f} 帧/秒，采集失败 {event.capture_failures} 次"
        )
        self._mark_sensor_received("ov5640", event.ts_ms)
        self.peripheral_panel.set_value("ov5640", self._peripheral_status("在线" if event.valid else "异常", event.fps, event.ts_ms))

    def apply_motion(self, event: MotionEvent) -> None:
        if event.accel_norm_g is None:
            self._mark_sensor_received("mpu6050", event.ts_ms)
            self.peripheral_panel.set_value("mpu6050", self._peripheral_status("兼容旧协议", None, event.ts_ms))
            return
        self._mark_sensor_received("mpu6050", event.ts_ms)
        self.peripheral_panel.set_value("mpu6050", self._peripheral_status("在线", 100.0, event.ts_ms, unit="Hz"))
        self.realtime_panel.set_value(
            "mpu6050", f"{event.accel_norm_g:.2f} g\n{event.tilt_deg or 0.0:.1f}° {'冲击' if event.impact else '正常'}",
        )
        self.derived_values["mpu6050"].setText("本机视觉/MPU 仲裁\n远端事件不改变气动")

    def apply_pressure(self, sample: PressureSample) -> None:
        self._last_pressure_sample = sample
        self._mark_sensor_received("pressure", sample.ts_ms)
        self.peripheral_panel.set_value("pressure", self._peripheral_status("在线" if sample.valid else "无效", 2.0, sample.ts_ms, unit="Hz"))
        self.refresh_sensor_freshness()
        self.derived_values["pressure"].setText("策略建议与真实执行分离\n等待泵阀真实反馈")

    def _mark_sensor_received(self, key: str, source_ts_ms: int) -> None:
        self._sensor_received_at_ms[key] = QtCore.QDateTime.currentMSecsSinceEpoch()
        self._sensor_source_ts_ms[key] = source_ts_ms

    def _peripheral_status(self, state: str, rate: float | None, source_ts_ms: int, *, unit: str = "帧/秒") -> str:
        wall_time = QtCore.QDateTime.currentDateTime().toString("HH:mm:ss")
        rate_text = "—" if rate is None else f"{rate:.1f} {unit}"
        return f"{state}\n采样率 {rate_text} · 更新 {wall_time}\n设备时间 {source_ts_ms} ms"

    def refresh_sensor_freshness(self) -> None:
        sample = self._last_pressure_sample
        received = self._sensor_received_at_ms.get("pressure")
        if sample is None or received is None:
            return
        age_ms = max(0, QtCore.QDateTime.currentMSecsSinceEpoch() - received)
        self.realtime_panel.set_value(
            "pressure", f"{sample.filtered_kpa:.2f} kPa\n{'有效' if sample.valid else '无效'} · 新鲜度 {age_ms} ms",
        )

    def apply_voice_status(self, event: VoiceStatusEvent) -> None:
        labels = {"ready": "就绪", "playing": "播放中", "finished": "已完成", "error": "错误", "initializing": "初始化"}
        text = f"DFPlayer · {labels.get(event.state, '未知')}"
        if event.track:
            text += f" · 曲目 {event.track}"
        if event.error:
            text += f" · {event.error}"
        self.voice_status_value.setText(text)
        self.derived_values["mpu6050"].setText(
            f"RGB 由仲裁层控制\n{text.replace('DFPlayer · ', 'DFPlayer ')} · 远端专用语音未配置"
        )

    def apply_health(self, health: dict) -> None:
        model_state = str(health.get("model_state") or "loading")
        gpu = "显卡加速" if str(health.get("gpu") or health.get("device") or "cuda").lower() == "cuda" else "处理器运算"
        color = (
            STATUS_COLORS["low"] if model_state == "ready"
            else STATUS_COLORS["fault"] if model_state == "error"
            else STATUS_COLORS["loading"]
        )
        self.model_value.setText(f"视觉模型 · {gpu} · {_state_label(model_state)}")
        self.model_stage.set_state(f"{_state_label(model_state)} · {gpu}", color)
        self.decision_model.setText(f"{_state_label(model_state)} · {gpu}")
        if model_state == "ready":
            self._set_system_status("等待首帧", "loading")
        elif model_state == "error":
            self._set_system_status("模型异常", "fault")
        else:
            self._set_system_status("模型加载中", "loading")
        if self._last_state:
            return
        if model_state == "ready":
            self.risk_band.setText("等待视觉帧")
            self.result_state.setText("● 等待首帧")
            self._apply_risk_tint("loading")
            self.risk_reason.setText("视觉模型已就绪，等待视觉帧；头盔设备将主动上传首帧。")
        elif model_state == "error":
            self.risk_band.setText("模型错误")
            self.result_state.setText("● 模型异常")
            self._apply_risk_tint("fault")
            self.risk_reason.setText(str(health.get("model_error") or "视觉模型加载失败。"))
        else:
            self.risk_band.setText("模型加载中")
            self.result_state.setText("● 模型加载中")
            self._apply_risk_tint("loading")
            self.risk_reason.setText("画面接收服务已就绪，视觉模型正在后台加载。")

    def apply_action_status(self, event: ActionStatusEvent) -> None:
        self.protocol_log.appendPlainText(
            f"动作状态：第 {event.frame_seq} 帧，{_state_label(event.action_state)}，"
            f"{_rgb_pattern_label(event.rgb_pattern)}，结果{'已失效' if event.stale else '有效'}"
        )
        if self._last_display_frame_seq >= 0 and event.frame_seq != self._last_display_frame_seq:
            self.protocol_log.appendPlainText(
                f"已忽略非当前展示帧的动作状态：展示第 {self._last_display_frame_seq} 帧，收到第 {event.frame_seq} 帧"
            )
            return
        band = "fault" if event.stale or event.action_state == "fault" else (
            event.action_state if event.action_state in STATUS_COLORS else "loading"
        )
        color = STATUS_COLORS[band]
        self.action_name.setText({
            "loading": "启动提示", "safe": "安全提示", "attention": "注意提示",
            "high": "高风险提示", "critical": "严重提示", "fault": "故障提示",
        }.get(event.action_state, "状态未知"))
        self.action_pattern.setText(f"板载指示灯 · {_rgb_pattern_label(event.rgb_pattern)} · 亮度 20%")
        self.action_ack.setText(f"串口动作状态 · 第 {event.frame_seq} 帧")
        self.action_stage.set_state(f"串口已确认 · 第 {event.frame_seq} 帧", color)
        self.action_indicator.setStyleSheet(f"background: {color}; border: none; border-radius: 2px;")

    def apply_pneumatic_status(self, event: PneumaticStatusEvent) -> None:
        self.pneumatic_panel.apply_status(event)
        self.pneumatic_summary.setText(
            f"气动执行器 · {event.state} · 泵{'开' if event.pump_on else '关'} · "
            f"阀{'通电' if event.valve_on else '断电泄压'} · 故障 {event.fault}"
        )
        self.derived_values["pressure"].setText(
            f"策略建议：{event.vision_state if event.vision_fresh else '禁止（视觉不新鲜）'}\n"
            f"真实执行：泵{'开' if event.pump_on else '关'} · 阀{'通电' if event.valve_on else '断电'}"
        )

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
        color = STATUS_COLORS.get(band, STATUS_COLORS["loading"])
        score = int(risk.get("score", 0)) if risk.get("valid") and not is_stale else None
        band_labels = {
            "loading": "模型加载中", "low": "低风险", "attention": "需要注意",
            "high": "高风险", "critical": "严重风险", "fault": "结果失效",
        }
        action_labels = {
            "loading": "启动提示", "safe": "安全提示", "attention": "注意提示",
            "high": "高风险提示", "critical": "严重提示", "fault": "故障提示",
        }
        self.device_value.setText(f"{_device_label(state.get('device_id'))} · {_state_label(upload.get('state'))}")
        gpu_label = "显卡加速" if str(model.get("gpu", "cuda")).lower() == "cuda" else "处理器运算"
        self.model_value.setText(f"视觉模型 · {gpu_label} · {_state_label(model_state)}")
        self.upload_stage.set_state(
            f"{float(upload.get('fps', 0)):.2f} 帧/秒 · 第 {int(upload.get('last_frame_seq', -1))} 帧",
            STATUS_COLORS["low"] if upload.get("state") == "healthy" else STATUS_COLORS["fault"],
        )
        model_latency = model.get("latency_ms")
        self.model_stage.set_state(
            f"{_state_label(model_state)} · {model_latency:.0f} 毫秒" if isinstance(model_latency, (int, float)) else _state_label(model_state),
            STATUS_COLORS["low"] if model_state == "ready" else STATUS_COLORS["loading"] if model_state == "loading" else STATUS_COLORS["fault"],
        )
        callback_latency = callback.get("latency_ms")
        self.action_stage.set_state(
            f"{_state_label(callback.get('state'))} · 第 {int(action.get('frame_seq', -1))} 帧",
            color,
        )
        self.risk_score.setText(f"{score:02d}" if score is not None else "--")
        self.risk_band.setText(band_labels.get(band, "状态未知"))
        self.result_state.setText(
            "● 结果已失效" if is_stale else "● 结果有效" if score is not None else "● 等待模型"
        )
        self.risk_gauge.setValue(score if score is not None else 0)
        self._apply_risk_tint(band)
        self.risk_reason.setText(_risk_reason_label(risk.get("reason"), model_state=model_state, stale=is_stale))
        self.realtime_panel.set_value(
            "ov5640",
            f"{risk.get('dominant_class') or '目标未知'}\n{score if score is not None else '—'} 分 · {'失效' if is_stale else '有效'}",
        )
        action_state = str(action.get("state", "loading"))
        pattern = str(action.get("rgb_pattern", "blue_blink_1hz"))
        self.derived_values["ov5640"].setText(
            f"{action_labels.get(action_state, '状态未知')}\n第 {action.get('frame_seq', '—')} 帧 · {'失效' if is_stale else '有效'}"
        )
        self.action_name.setText(action_labels.get(action_state, "状态未知"))
        self.action_pattern.setText(f"板载指示灯 · {_rgb_pattern_label(pattern)} · 亮度 20%")
        if action.get("confirmed"):
            ack_text = f"动作已确认 · 第 {int(action.get('frame_seq', -1))} 帧"
            e2e_latency = action.get("e2e_latency_ms")
            if isinstance(e2e_latency, (int, float)) and e2e_latency >= 0:
                ack_text += f" · 端到端 {int(round(float(e2e_latency)))} 毫秒"
            self.action_ack.setText(ack_text)
        else:
            self.action_ack.setText("等待动作确认")
        self.execution_guard.setText(
            "旧数据、断链或无效数据：不生成新的执行结论。"
            if is_stale or not risk.get("valid") else "数据新鲜且有效：展示策略建议；真实执行以串口反馈为准。"
        )
        age = upload.get("frame_age_ms")
        frame_seq = int(display.get("frame_seq", -1)) if display.get("ready") else int(risk.get("frame_seq", upload.get("last_frame_seq", -1)) or -1)
        risk_frame_seq = int(risk.get("frame_seq", -1) or -1)
        if score is not None and risk_frame_seq >= 0 and risk_frame_seq != self._last_trend_frame:
            self._last_trend_frame = risk_frame_seq
            self.risk_trend.add_score(score)
        self.camera_uplink.setText(
            f"传输状态 · {float(upload.get('fps', 0)):.2f} 帧/秒 · 第 {frame_seq} 帧"
            if frame_seq >= 0 else "传输状态 · 等待首帧"
        )
        if is_stale:
            self._set_system_status("闭环异常", "fault")
        elif model_state == "loading":
            self._set_system_status("模型加载中", "loading")
        elif (
            upload.get("state") == "healthy"
            and callback.get("state") == "confirmed"
            and action.get("confirmed")
        ):
            self._set_system_status("闭环运行正常", band if band in STATUS_COLORS else "low")
        else:
            self._set_system_status("链路连接中", "loading")
        boot_id = str(state.get("boot_id") or "")
        frame_text = f"第 {frame_seq:08d} 帧" if frame_seq >= 0 else "等待视觉帧"
        if boot_id:
            frame_text += f" · 启动标识 {boot_id[-4:].upper()}"
        model_detail = f"{_state_label(model_state)} · {gpu_label}"
        if isinstance(model_latency, (int, float)):
            model_detail += f" · {float(model_latency):.0f} 毫秒"
        callback_detail = _state_label(callback.get("state"))
        if isinstance(callback_latency, (int, float)):
            callback_detail += f" · {float(callback_latency):.0f} 毫秒"
        attempts = int(callback.get("attempts", 0) or 0)
        if attempts:
            callback_detail += f" · 尝试 {attempts} 次"
        freshness_detail = (
            f"{int(age)} 毫秒 · {float(upload.get('fps', 0)):.2f} 帧/秒"
            if isinstance(age, (int, float)) else f"— 毫秒 · {float(upload.get('fps', 0)):.2f} 帧/秒"
        )
        self.decision_frame.setText(frame_text)
        self.decision_model.setText(model_detail)
        self.decision_callback.setText(callback_detail)
        self.decision_freshness.setText(freshness_detail)
        self.decision_counts.setText(
            f"接收 {int(upload.get('accepted_frames', 0) or 0)} · "
            f"分析 {int(model.get('valid_results', 0) or 0)} · "
            f"确认 {int(callback.get('confirmed_count', 0) or 0)}"
        )
        self.upload_fps.value.setText(f"{float(upload.get('fps', 0)):.2f} 帧/秒")
        self.frame_age.value.setText(f"{int(age)} 毫秒" if isinstance(age, (int, float)) else "—")
        self.infer_latency.value.setText(f"{float(model_latency):.0f} 毫秒" if isinstance(model_latency, (int, float)) else "—")
        self.callback_latency.value.setText(f"{float(callback_latency):.0f} 毫秒" if isinstance(callback_latency, (int, float)) else "—")
        self.action_frame.value.setText(f"第 {action.get('frame_seq')} 帧" if isinstance(action.get("frame_seq"), int) and action.get("frame_seq") >= 0 else "—")
        self.last_error.value.setText(_error_label(state.get("last_error")))
        self.chain_log.appendPlainText(
            f"第 {upload.get('last_frame_seq')} 帧：上传{_state_label(upload.get('state'))}，"
            f"模型{_state_label(model_state)}，回传{_state_label(callback.get('state'))}，动作{_state_label(action_state)}"
        )

    def set_session_path(self, path: str) -> None:
        self.session_log.setPlainText(path)
