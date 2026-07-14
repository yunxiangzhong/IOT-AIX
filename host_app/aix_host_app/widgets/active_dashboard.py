from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

from ..models import ActionStatusEvent, CameraStatusEvent


STATUS_COLORS = {
    "loading": "#315F89",
    "low": "#2E704B",
    "attention": "#A46B12",
    "high": "#C45121",
    "critical": "#A72F2F",
    "fault": "#704A80",
}


class _Stage(QtWidgets.QFrame):
    def __init__(self, index: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("chainStage")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)
        heading = QtWidgets.QHBoxLayout()
        number = QtWidgets.QLabel(index)
        number.setObjectName("monoMuted")
        self.dot = QtWidgets.QLabel("●")
        self.dot.setObjectName("stageDot")
        label = QtWidgets.QLabel(title)
        label.setObjectName("stageTitle")
        heading.addWidget(number)
        heading.addWidget(self.dot)
        heading.addWidget(label, 1)
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


class ActiveVisionDashboard(QtWidgets.QWidget):
    settings_requested = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._last_image: QtGui.QImage | None = None
        self._last_state: dict = {}
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

    def _build_header(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("instrumentHeader")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(14, 8, 10, 8)
        title = QtWidgets.QLabel("AIX 主动视觉控制台")
        title.setObjectName("instrumentTitle")
        subtitle = QtWidgets.QLabel("ACTIVE VISION INSTRUMENT / V1")
        subtitle.setObjectName("instrumentSubtitle")
        titles = QtWidgets.QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        layout.addLayout(titles, 1)
        self.device_value = QtWidgets.QLabel("aix-helmet-01 · 等待")
        self.device_value.setObjectName("headerTelemetry")
        self.model_value = QtWidgets.QLabel("DA3-SMALL · 加载中")
        self.model_value.setObjectName("headerTelemetry")
        layout.addWidget(self.device_value)
        layout.addWidget(self.model_value)
        self.display_button = QtWidgets.QPushButton("展示")
        self.diagnostic_button = QtWidgets.QPushButton("诊断")
        self.settings_button = QtWidgets.QPushButton("设置")
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
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.camera_stage = _Stage("01", "OV5640 采集")
        self.upload_stage = _Stage("02", "ESP 主动上传")
        self.model_stage = _Stage("03", "PC 异步推理")
        self.action_stage = _Stage("04", "ESP 动作确认")
        for stage in (self.camera_stage, self.upload_stage, self.model_stage, self.action_stage):
            layout.addWidget(stage, 1)
        return frame

    def _build_workspace(self) -> QtWidgets.QSplitter:
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        camera = QtWidgets.QFrame()
        camera.setObjectName("instrumentPanel")
        camera_layout = QtWidgets.QVBoxLayout(camera)
        camera_layout.setContentsMargins(0, 0, 0, 0)
        camera_layout.setSpacing(0)
        camera_head = QtWidgets.QFrame()
        camera_head.setObjectName("panelHead")
        head_layout = QtWidgets.QHBoxLayout(camera_head)
        head_layout.setContentsMargins(12, 6, 12, 6)
        head_layout.addWidget(QtWidgets.QLabel("实时视野"))
        self.frame_telemetry = QtWidgets.QLabel("等待 PC 最新帧")
        self.frame_telemetry.setObjectName("monoMuted")
        head_layout.addWidget(self.frame_telemetry, 1, QtCore.Qt.AlignmentFlag.AlignRight)
        self.camera_image = QtWidgets.QLabel("PC 帧服务尚未提供画面")
        self.camera_image.setObjectName("activeCamera")
        self.camera_image.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.camera_image.setMinimumSize(640, 360)
        camera_layout.addWidget(camera_head)
        camera_layout.addWidget(self.camera_image, 1)

        decision = QtWidgets.QFrame()
        decision.setObjectName("instrumentPanel")
        decision_layout = QtWidgets.QVBoxLayout(decision)
        decision_layout.setContentsMargins(18, 16, 18, 16)
        decision_layout.setSpacing(8)
        heading = QtWidgets.QLabel("相对视觉风险")
        heading.setObjectName("metricTitle")
        self.risk_score = QtWidgets.QLabel("--")
        self.risk_score.setObjectName("riskScore")
        self.risk_band = QtWidgets.QLabel("模型加载中")
        self.risk_band.setObjectName("riskBand")
        self.risk_reason = QtWidgets.QLabel("HTTP 服务启动后即可接收 JPEG；模型在后台加载。")
        self.risk_reason.setObjectName("muted")
        self.risk_reason.setWordWrap(True)
        divider = QtWidgets.QFrame()
        divider.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        self.action_name = QtWidgets.QLabel("启动提示")
        self.action_name.setObjectName("actionName")
        self.action_pattern = QtWidgets.QLabel("GPIO38 · BLUE_BLINK_1HZ · 20%")
        self.action_pattern.setObjectName("metricMono")
        self.action_ack = QtWidgets.QLabel("等待 ACTION_ACK")
        self.action_ack.setObjectName("monoMuted")
        for widget in (heading, self.risk_score, self.risk_band, self.risk_reason, divider, self.action_name, self.action_pattern):
            decision_layout.addWidget(widget)
        decision_layout.addStretch(1)
        decision_layout.addWidget(self.action_ack)

        splitter.addWidget(camera)
        splitter.addWidget(decision)
        splitter.setSizes([700, 300])
        return splitter

    def _build_metrics(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("metricBand")
        layout = QtWidgets.QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.upload_fps = _Metric("上传 FPS")
        self.frame_age = _Metric("帧年龄")
        self.infer_latency = _Metric("推理延迟")
        self.callback_latency = _Metric("回调延迟")
        self.action_frame = _Metric("确认帧")
        self.last_error = _Metric("最后错误")
        for metric in (self.upload_fps, self.frame_age, self.infer_latency, self.callback_latency, self.action_frame, self.last_error):
            layout.addWidget(metric, 1)
        return frame

    def _build_diagnostics(self) -> QtWidgets.QTabWidget:
        tabs = QtWidgets.QTabWidget()
        tabs.setObjectName("diagnostics")
        self.chain_log = QtWidgets.QPlainTextEdit()
        self.protocol_log = QtWidgets.QPlainTextEdit()
        self.device_log = QtWidgets.QPlainTextEdit("压力传感器：等待串口\n速度：未接入\n加速度：未接入\n气囊/气泵：未接入")
        self.session_log = QtWidgets.QPlainTextEdit("会话尚未开始")
        for widget in (self.chain_log, self.protocol_log, self.device_log, self.session_log):
            widget.setReadOnly(True)
            widget.setMaximumBlockCount(500)
        tabs.addTab(self.chain_log, "链路")
        tabs.addTab(self.protocol_log, "协议")
        tabs.addTab(self.device_log, "设备")
        tabs.addTab(self.session_log, "会话")
        tabs.setMaximumHeight(220)
        return tabs

    def set_diagnostic_mode(self, enabled: bool) -> None:
        self.diagnostics.setVisible(enabled)
        self.display_button.setChecked(not enabled)
        self.diagnostic_button.setChecked(enabled)

    def apply_frame(self, data: bytes, frame_seq: int, capture_ts_ms: int) -> bool:
        image = QtGui.QImage.fromData(data, "JPG")
        if image.isNull():
            return False
        self._last_image = image
        self.frame_telemetry.setText(f"frame {frame_seq:08d} · capture {capture_ts_ms} ms")
        self._render_image()
        return True

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_image()

    def _render_image(self) -> None:
        if self._last_image is None:
            return
        pixmap = QtGui.QPixmap.fromImage(self._last_image).scaled(
            self.camera_image.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.camera_image.setPixmap(pixmap)

    def apply_camera_status(self, event: CameraStatusEvent) -> None:
        color = STATUS_COLORS["low"] if event.valid else STATUS_COLORS["fault"]
        self.camera_stage.set_state(f"{event.width}×{event.height} JPEG · {event.fps:.2f} FPS", color)
        self.device_log.appendPlainText(
            f"OV5640 frame={event.frames_ok} fps={event.fps:.2f} failures={event.capture_failures} valid={event.valid}"
        )

    def apply_action_status(self, event: ActionStatusEvent) -> None:
        self.protocol_log.appendPlainText(
            f"action_status frame={event.frame_seq} state={event.action_state} rgb={event.rgb_pattern} stale={event.stale}"
        )
        band = "fault" if event.stale or event.action_state == "fault" else (
            "critical" if event.risk_score >= 80 else "high" if event.risk_score >= 60
            else "attention" if event.risk_score >= 30 else "low"
        )
        color = STATUS_COLORS[band]
        self.risk_score.setText("--" if band == "fault" else f"{event.risk_score:02d}")
        self.risk_score.setStyleSheet(f"color: {color}; background: transparent;")
        self.risk_band.setText({
            "fault": "结果失效", "low": "低风险", "attention": "需要注意",
            "high": "高风险", "critical": "严重风险",
        }[band])
        self.risk_band.setStyleSheet(f"color: {color}; background: transparent;")
        if band == "fault":
            self.risk_reason.setText("ESP 报告视觉结果超过 3 秒失效或链路故障，旧风险已隔离。")
        self.action_name.setText({
            "loading": "启动提示", "safe": "安全提示", "attention": "注意提示",
            "high": "高风险提示", "critical": "严重提示", "fault": "故障提示",
        }.get(event.action_state, "状态未知"))
        self.action_pattern.setText(f"GPIO38 · {event.rgb_pattern.upper()} · 20%")
        self.action_ack.setText(f"SERIAL ACTION_STATUS · frame {event.frame_seq}")
        self.action_stage.set_state(f"serial confirmed · frame {event.frame_seq}", color)

    def apply_chain_state(self, state: dict) -> None:
        self._last_state = state
        upload = state.get("upload", {})
        model = state.get("model", {})
        callback = state.get("callback", {})
        risk = state.get("risk", {})
        action = state.get("action", {})
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
        self.device_value.setText(f"{state.get('device_id', 'aix-helmet-01')} · {upload.get('state', 'waiting')}")
        self.model_value.setText(f"DA3-SMALL · {str(model.get('gpu', 'cuda')).upper()} · {model_state}")
        self.upload_stage.set_state(
            f"{float(upload.get('fps', 0)):.2f} FPS · frame {int(upload.get('last_frame_seq', -1))}",
            STATUS_COLORS["low"] if upload.get("state") == "healthy" else STATUS_COLORS["fault"],
        )
        model_latency = model.get("latency_ms")
        self.model_stage.set_state(
            f"{model_state} · {model_latency:.0f} ms" if isinstance(model_latency, (int, float)) else model_state,
            STATUS_COLORS["low"] if model_state == "ready" else STATUS_COLORS["loading"] if model_state == "loading" else STATUS_COLORS["fault"],
        )
        callback_latency = callback.get("latency_ms")
        self.action_stage.set_state(
            f"{callback.get('state', 'waiting')} · frame {int(action.get('frame_seq', -1))}",
            color,
        )
        self.risk_score.setText(f"{score:02d}" if score is not None else "--")
        self.risk_score.setStyleSheet(f"color: {color}; background: transparent;")
        self.risk_band.setText(band_labels.get(band, "状态未知"))
        self.risk_band.setStyleSheet(f"color: {color}; background: transparent;")
        self.risk_reason.setText(
            "超过 3 秒未收到新鲜合法结果，旧风险已隔离。" if is_stale
            else str(risk.get("reason") or ("模型正在后台加载。" if model_state == "loading" else "等待风险结果。"))
        )
        action_state = str(action.get("state", "loading"))
        pattern = str(action.get("rgb_pattern", "blue_blink_1hz"))
        self.action_name.setText(action_labels.get(action_state, "状态未知"))
        self.action_pattern.setText(f"GPIO38 · {pattern.upper()} · 20%")
        self.action_ack.setText(
            f"ACTION_ACK · frame {int(action.get('frame_seq', -1))}" if action.get("confirmed") else "等待 ACTION_ACK"
        )
        age = upload.get("frame_age_ms")
        self.upload_fps.value.setText(f"{float(upload.get('fps', 0)):.2f}")
        self.frame_age.value.setText(f"{int(age)} ms" if isinstance(age, (int, float)) else "—")
        self.infer_latency.value.setText(f"{float(model_latency):.0f} ms" if isinstance(model_latency, (int, float)) else "—")
        self.callback_latency.value.setText(f"{float(callback_latency):.0f} ms" if isinstance(callback_latency, (int, float)) else "—")
        self.action_frame.value.setText(str(action.get("frame_seq", "—")))
        self.last_error.value.setText(str(state.get("last_error") or "—"))
        self.chain_log.appendPlainText(
            f"frame={upload.get('last_frame_seq')} upload={upload.get('state')} model={model_state} callback={callback.get('state')} action={action_state}"
        )

    def set_session_path(self, path: str) -> None:
        self.session_log.setPlainText(path)
