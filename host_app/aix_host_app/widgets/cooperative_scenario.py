from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


_COLORS = {"waiting": "#8E8E93", "active": "#007AFF", "completed": "#248A3D", "failed": "#D70015"}


class _RoadView(QtWidgets.QFrame):
    """A deliberately illustrative view: it is never presented as a camera frame."""

    def __init__(self, title: str, subtitle: str, *, roadside: bool, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scenePanel")
        self._roadside = roadside
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        title_label = QtWidgets.QLabel(title)
        title_label.setObjectName("panelTitle")
        self.caption = QtWidgets.QLabel(subtitle)
        self.caption.setObjectName("softBadge")
        layout.addWidget(title_label)
        layout.addWidget(self.caption)
        self.canvas = QtWidgets.QWidget()
        self.canvas.setMinimumHeight(230)
        self.canvas.setAccessibleName(f"{title}场景模拟")
        self.canvas.paintEvent = self._paint  # type: ignore[method-assign]
        layout.addWidget(self.canvas, 1)

    def _paint(self, event) -> None:
        painter = QtGui.QPainter(self.canvas)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        r = self.canvas.rect().adjusted(4, 4, -4, -4)
        painter.fillRect(r, QtGui.QColor("#EAF3FF"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#AAB8C5"), 3))
        painter.drawLine(r.left(), r.bottom() - 12, r.right(), r.top() + 42)
        painter.drawLine(r.left() + 28, r.bottom(), r.right(), r.top() + 70)
        truck = QtCore.QRect(r.right() - r.width() // 3, r.top() + r.height() // 3, r.width() // 4, r.height() // 4)
        painter.fillRect(truck, QtGui.QColor("#FF9F0A"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#D70015"), 2))
        painter.drawRect(truck.adjusted(-5, -5, 5, 5))
        painter.setPen(QtGui.QColor("#1D1D1F"))
        text = "右侧货车 · ETA 5 秒" if self._roadside else "右侧盲区 · 骑行者不可见"
        painter.drawText(r.adjusted(12, 12, -12, -12), QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft, text)


class _ScenarioStage(QtWidgets.QFrame):
    def __init__(self, index: int, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("chainStage")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 9, 10, 9)
        title_label = QtWidgets.QLabel(f"{index}. {title}")
        title_label.setObjectName("panelTitle")
        self.meta = QtWidgets.QLabel("等待")
        self.meta.setObjectName("monoMuted")
        layout.addWidget(title_label)
        layout.addWidget(self.meta)

    def set_state(self, text: str, state: str) -> None:
        self.meta.setText(text)
        self.meta.setStyleSheet(f"color: {_COLORS.get(state, _COLORS['waiting'])}; background: transparent;")


class CooperativeScenarioPanel(QtWidgets.QWidget):
    start_requested = QtCore.Signal(dict)
    reset_requested = QtCore.Signal()

    EVENT_ID = "demo-truck-right-5s"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running = False
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        heading = QtWidgets.QFrame()
        heading.setObjectName("instrumentHeader")
        h = QtWidgets.QHBoxLayout(heading)
        h.setContentsMargins(18, 12, 18, 12)
        title = QtWidgets.QLabel("路侧协同预警 · 货车右侧盲区")
        title.setObjectName("instrumentTitle")
        detail = QtWidgets.QLabel("场景模拟：路侧识别与 ETA 是演示输入；最终确认仅来自 ESP32 ACK")
        detail.setObjectName("instrumentSubtitle")
        labels = QtWidgets.QVBoxLayout()
        labels.addWidget(title)
        labels.addWidget(detail)
        h.addLayout(labels, 1)
        self.start_button = QtWidgets.QPushButton("开始货车盲区演示")
        self.start_button.setObjectName("primaryAction")
        self.reset_button = QtWidgets.QPushButton("复位")
        self.start_button.clicked.connect(self.begin_demo)
        self.reset_button.clicked.connect(self.reset_demo)
        h.addWidget(self.start_button)
        h.addWidget(self.reset_button)
        root.addWidget(heading)

        views = QtWidgets.QHBoxLayout()
        views.setSpacing(12)
        views.addWidget(_RoadView("骑行者盲区视角", "场景模拟 · 右侧遮挡", roadside=False), 1)
        views.addWidget(_RoadView("路侧摄像头视角", "场景模拟 · 检测货车 0.94 · 右侧", roadside=True), 1)
        root.addLayout(views, 1)

        stages = QtWidgets.QHBoxLayout()
        stages.setSpacing(8)
        self.stages = [
            _ScenarioStage(1, "路侧采集"), _ScenarioStage(2, "云端识别"),
            _ScenarioStage(3, "到达预测"), _ScenarioStage(4, "下发头盔"),
            _ScenarioStage(5, "ESP32 确认"),
        ]
        for stage in self.stages:
            stages.addWidget(stage, 1)
        root.addLayout(stages)

        info = QtWidgets.QFrame()
        info.setObjectName("panel")
        grid = QtWidgets.QGridLayout(info)
        grid.setContentsMargins(14, 10, 14, 10)
        self.event_value = self._value("事件 ID · 等待演示")
        self.network_value = self._value("网络耗时 · —")
        self.rgb_value = self._value("RGB · 等待 ACK")
        self.voice_value = self._value("语音 · 专用语音未配置")
        self.serial_status = self._value("串口状态 · 等待")
        for i, value in enumerate((self.event_value, self.network_value, self.rgb_value, self.voice_value, self.serial_status)):
            grid.addWidget(value, i // 3, i % 3)
        root.addWidget(info)
        self.reset_demo()

    @staticmethod
    def _value(text: str) -> QtWidgets.QLabel:
        value = QtWidgets.QLabel(text)
        value.setObjectName("metricMono")
        return value

    def demo_payload(self) -> dict:
        return {
            "event_id": self.EVENT_ID, "device_id": "aix-helmet-01", "camera_id": "roadside-cam-01",
            "intersection_id": "demo-crossing-01", "direction": "right", "object_type": "truck",
            "eta_ms": 5000, "severity": "high", "ttl_ms": 7000, "simulated": True,
            "message_code": "truck_right_eta_5s",
        }

    def begin_demo(self) -> None:
        if self._running:
            return
        self._running = True
        self.start_button.setEnabled(False)
        self.event_value.setText(f"事件 ID · {self.EVENT_ID}")
        for index, text in enumerate(("已采集 · 场景模拟", "货车 · 0.94", "右侧 · ETA 5 秒", "正在下发", "等待真实 ACK")):
            self.stages[index].set_state(text, "completed" if index < 3 else "active" if index == 3 else "waiting")
        self.start_requested.emit(self.demo_payload())

    def reset_demo(self) -> None:
        self._running = False
        self.start_button.setEnabled(True)
        for stage in self.stages:
            stage.set_state("等待", "waiting")
        self.event_value.setText("事件 ID · 等待演示")
        self.network_value.setText("网络耗时 · —")
        self.rgb_value.setText("RGB · 等待 ACK")
        self.voice_value.setText("语音 · 专用语音未配置")
        self.serial_status.setText("串口状态 · 等待")
        self.reset_requested.emit()

    def apply_chain_state(self, state: dict) -> None:
        hazard = state.get("road_hazard") if isinstance(state, dict) else None
        if not isinstance(hazard, dict) or not hazard.get("event_id"):
            return
        self.event_value.setText(f"事件 ID · {hazard.get('event_id')}")
        for stage, key in zip(self.stages[:3], ("roadside_capture", "cloud_recognition", "arrival_prediction")):
            item = hazard.get(key, {})
            complete = item.get("state") == "completed"
            stage.set_state("已完成" if complete else "等待", "completed" if complete else "waiting")
        delivery = hazard.get("delivery", {})
        attempts = int(hazard.get("attempts", 0) or 0)
        delivery_state = str(delivery.get("state", "waiting"))
        delivery_text = "下发完成" if delivery_state == "completed" else f"失败 · 已重试 {attempts} 次" if delivery_state == "failed" else f"下发中 · 第 {attempts + 1} 次" if delivery_state == "active" else "等待下发"
        self.stages[3].set_state(delivery_text, "completed" if delivery_state == "completed" else "failed" if delivery_state == "failed" else "active" if delivery_state == "active" else "waiting")
        ack = hazard.get("ack", {})
        payload = ack.get("payload") if isinstance(ack, dict) else None
        real_ack = isinstance(payload, dict) and payload.get("type") == "road_hazard_ack" and payload.get("accepted") is True and payload.get("event_id") == hazard.get("event_id")
        if real_ack:
            self.stages[4].set_state("真实 ACK 已确认", "completed")
        elif delivery_state == "failed" or (isinstance(ack, dict) and ack.get("state") == "failed"):
            self.stages[4].set_state("未确认 · ESP32 离线或拒绝", "failed")
        else:
            self.stages[4].set_state("等待真实 ACK", "waiting")
        latency = hazard.get("network_latency_ms")
        self.network_value.setText(f"网络耗时 · {int(latency)} 毫秒" if isinstance(latency, (int, float)) else "网络耗时 · —")
        pattern = str(hazard.get("effective_rgb_pattern") or "")
        self.rgb_value.setText(f"RGB · {pattern}" if pattern else "RGB · 等待 ACK")

    def apply_serial_status(self, event) -> None:
        self.serial_status.setText(f"串口状态 · {event.state} · {event.event_id or '—'}")
        if event.effective_rgb_pattern:
            self.rgb_value.setText(f"RGB · {event.effective_rgb_pattern}")
