from __future__ import annotations

import uuid

from PySide6 import QtCore, QtGui, QtWidgets


_COLORS = {"waiting": "#86868B", "active": "#007AFF", "completed": "#248A3D", "failed": "#D70015"}


class _CrossroadMap(QtWidgets.QWidget):
    """Focused L-corner view: only the truck's right approach and rider's lower approach."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.progress = 0.0
        self.eta_seconds = 5.0
        self.phase = "等待演示"
        self.reduced_motion = False
        self.rider_lane = "northbound_right"
        self.rider_progress = 0.0
        self.rider_slowed = False
        self.rider_speed_kmh = 18
        self.setMinimumSize(560, 380)
        self.setAccessibleName("十字路口货车盲区协同预警模拟")

    def set_state(
        self, progress: float, eta_seconds: float, phase: str, *,
        rider_progress: float = 0.0, rider_slowed: bool = False, rider_speed_kmh: int = 18,
    ) -> None:
        progress = max(0.0, min(1.0, progress))
        if self.reduced_motion:
            progress = round(progress * 5) / 5
        self.progress = progress
        self.eta_seconds = max(0.0, eta_seconds)
        self.phase = phase
        self.rider_progress = max(0.0, min(1.0, rider_progress))
        self.rider_slowed = rider_slowed
        self.rider_speed_kmh = rider_speed_kmh
        self.setAccessibleDescription(f"货车距离路口约 {self.eta_seconds:.1f} 秒，当前阶段：{phase}")
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        bounds = self.rect().adjusted(8, 8, -8, -8)
        painter.fillRect(bounds, QtGui.QColor("#E7EFE7"))

        road = QtGui.QColor("#60646C")
        lane = QtGui.QColor("#D8D8DC")
        # Anchor the L-shaped intersection toward the upper-left so both relevant
        # approaches use the available canvas instead of leaving a large dead area.
        cx = int(bounds.left() + bounds.width() * 0.30)
        cy = int(bounds.top() + bounds.height() * 0.28)
        road_w = max(150, int(min(bounds.width(), bounds.height()) * 0.34))
        # The map intentionally contains only the two approaches relevant to this event:
        # truck from the right, rider from below. The unused upper/left arms are omitted.
        junction = QtCore.QRect(cx - road_w // 2, cy - road_w // 2, road_w, road_w)
        horizontal = QtCore.QRect(cx, cy - road_w // 2, bounds.right() - cx, road_w)
        vertical = QtCore.QRect(cx - road_w // 2, cy, road_w, bounds.bottom() - cy)
        painter.fillRect(junction, road)
        painter.fillRect(horizontal, road)
        painter.fillRect(vertical, road)

        dash_pen = QtGui.QPen(lane, 2, QtCore.Qt.PenStyle.DashLine)
        painter.setPen(dash_pen)
        painter.drawLine(cx, cy, bounds.right(), cy)
        painter.drawLine(cx, cy, cx, bounds.bottom())

        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.setBrush(QtGui.QColor("#F5F5F7"))
        stripe = 8
        for offset in range(-road_w // 2 + 10, road_w // 2 - 8, 18):
            painter.drawRect(cx + offset, cy + road_w // 2 + 4, stripe, 18)
            painter.drawRect(cx + road_w // 2 + 4, cy + offset, 18, stripe)

        # South-east building blocks the rider's view of traffic approaching from the right.
        building = QtCore.QRect(cx + road_w // 2 + 18, cy + road_w // 2 + 18,
                                max(80, bounds.right() - (cx + road_w // 2 + 28)),
                                max(80, bounds.bottom() - (cy + road_w // 2 + 28)))
        painter.setBrush(QtGui.QColor("#D4C8B6"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#A89984"), 2))
        painter.drawRoundedRect(building, 10, 10)
        painter.setPen(QtGui.QColor("#5C5144"))
        painter.drawText(building.adjusted(8, 8, -8, -8), QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft, "街角建筑\n遮挡视线")

        # The rider travels north in the right-hand lane (China right-side traffic).
        rider_start_y = bounds.bottom() - 44
        # A longer lower approach makes the rider movement readable before the stop line.
        rider_stop_y = cy + road_w * 0.64 + 30
        rider_y = rider_start_y + (rider_stop_y - rider_start_y) * self.rider_progress
        rider = QtCore.QPointF(cx + road_w * 0.19, rider_y)
        truck_start = bounds.right() - 58
        # ETA=0 means the truck nose has just reached the intersection stop line, never passed it.
        truck_end = cx + road_w * 0.66
        truck_x = truck_start + (truck_end - truck_start) * self.progress
        truck_center = QtCore.QPointF(truck_x, cy - road_w * 0.20)

        blind = QtGui.QPolygonF([rider, QtCore.QPointF(building.left(), building.bottom()), truck_center])
        blind_color = QtGui.QColor("#FF9F0A")
        blind_color.setAlpha(48)
        painter.setBrush(blind_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#C93400"), 2, QtCore.Qt.PenStyle.DashLine))
        painter.drawPolygon(blind)

        # Roadside camera and field of view.
        camera_pos = QtCore.QPointF(bounds.right() - 34, cy - road_w // 2 - 42)
        fov = QtGui.QPolygonF([camera_pos, QtCore.QPointF(cx + 20, cy - road_w // 2), QtCore.QPointF(bounds.right() - 15, cy + road_w // 2)])
        fov_color = QtGui.QColor("#007AFF")
        fov_color.setAlpha(32)
        painter.setBrush(fov_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#007AFF"), 1, QtCore.Qt.PenStyle.DashLine))
        painter.drawPolygon(fov)
        painter.setBrush(QtGui.QColor("#1D1D1F"))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QtCore.QRectF(camera_pos.x() - 13, camera_pos.y() - 8, 26, 16), 4, 4)
        painter.setPen(QtGui.QColor("#1D1D1F"))
        painter.drawText(int(camera_pos.x() - 118), int(camera_pos.y() - 22), 110, 20,
                         QtCore.Qt.AlignmentFlag.AlignRight, "路侧摄像头")

        # Truck body and detection box.
        truck = QtCore.QRectF(truck_center.x() - 34, truck_center.y() - 18, 68, 36)
        painter.setBrush(QtGui.QColor("#FF9F0A"))
        painter.setPen(QtGui.QPen(QtGui.QColor("#9C4A00"), 1))
        painter.drawRoundedRect(truck, 6, 6)
        painter.setBrush(QtGui.QColor("#2C2C2E"))
        painter.drawEllipse(QtCore.QPointF(truck.left() + 14, truck.bottom() + 2), 5, 5)
        painter.drawEllipse(QtCore.QPointF(truck.right() - 14, truck.bottom() + 2), 5, 5)
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.setPen(QtGui.QPen(QtGui.QColor("#D70015"), 2))
        painter.drawRoundedRect(truck.adjusted(-5, -5, 5, 5), 7, 7)
        painter.setPen(QtGui.QColor("#D70015"))
        truck_label_width = 174
        truck_label_x = min(
            int(truck.left() - 4),
            bounds.right() - truck_label_width - 6,
        )
        truck_label_x = max(bounds.left() + 6, truck_label_x)
        painter.drawText(truck_label_x, int(truck.top() - 24), truck_label_width, 20,
                         QtCore.Qt.AlignmentFlag.AlignLeft, f"货车 0.94 · ETA {self.eta_seconds:.1f}s")

        # Rider / helmet marker.
        rider_color = QtGui.QColor("#248A3D" if self.rider_slowed else "#007AFF")
        painter.setBrush(rider_color)
        painter.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 2))
        painter.drawEllipse(rider, 13, 13)
        painter.setPen(QtGui.QColor("#FFFFFF"))
        painter.drawText(QtCore.QRectF(rider.x() - 10, rider.y() - 10, 20, 20), QtCore.Qt.AlignmentFlag.AlignCenter, "H")
        painter.setPen(QtGui.QColor("#1D1D1F"))
        rider_label_y = min(int(rider.y() + 18), bounds.bottom() - 24)
        painter.drawText(int(rider.x() - 48), rider_label_y, 96, 20,
                         QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignTop, "骑行者 / 头盔")
        painter.setPen(QtGui.QPen(rider_color, 3))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 20), QtCore.QPointF(rider.x(), rider.y() - 48))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 48), QtCore.QPointF(rider.x() - 6, rider.y() - 39))
        painter.drawLine(QtCore.QPointF(rider.x(), rider.y() - 48), QtCore.QPointF(rider.x() + 6, rider.y() - 39))

        painter.setPen(QtGui.QColor("#248A3D" if self.rider_slowed else "#007AFF"))
        response_label = "已减速 · 6 km/h" if self.rider_slowed else f"正常骑行 · {self.rider_speed_kmh} km/h"
        painter.drawText(
            int(rider.x() - 64), max(bounds.top() + 12, int(rider.y() - 84)), 128, 18,
            QtCore.Qt.AlignmentFlag.AlignHCenter, response_label,
        )

        painter.setPen(QtGui.QColor("#6E6E73"))
        painter.drawText(bounds.adjusted(14, 12, -14, -12), QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.AlignmentFlag.AlignLeft,
                         f"十字路口 · 右侧盲区\n{self.phase}")


class _ScenarioStage(QtWidgets.QFrame):
    def __init__(self, index: int, title: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("scenarioStage")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)
        header = QtWidgets.QHBoxLayout()
        self.dot = QtWidgets.QLabel("●")
        self.dot.setObjectName("stageDot")
        title_label = QtWidgets.QLabel(f"{index:02d}  {title}")
        title_label.setObjectName("mappingLabel")
        header.addWidget(self.dot)
        header.addWidget(title_label, 1)
        self.meta = QtWidgets.QLabel("等待")
        self.meta.setObjectName("monoMuted")
        self.meta.setWordWrap(True)
        layout.addLayout(header)
        layout.addWidget(self.meta)
        self.set_state("等待", "waiting")

    def set_state(self, text: str, state: str) -> None:
        color = _COLORS.get(state, _COLORS["waiting"])
        self.meta.setText(text)
        self.dot.setStyleSheet(f"color: {color}; background: transparent;")
        self.setProperty("stageState", state)
        self.style().unpolish(self)
        self.style().polish(self)


class CooperativeScenarioPanel(QtWidgets.QWidget):
    start_requested = QtCore.Signal(dict)
    reset_requested = QtCore.Signal()

    EVENT_DURATION_MS = 5000
    CLOUD_DISPATCH_MS = 850

    @staticmethod
    def has_simulated_input() -> bool:
        """The collaboration page intentionally has a self-contained visual demo."""
        return True

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._running = False
        self._dispatched = False
        self._ack_received = False
        self._ack_remaining_ms: int | None = None
        self._ack_elapsed_ms: int | None = None
        self._ack_is_simulated = False
        self.current_event_id = ""
        self._reduced_motion = False
        self._clock = QtCore.QElapsedTimer()
        self._last_elapsed_ms = 0
        self._timer = QtCore.QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        heading = QtWidgets.QFrame()
        heading.setObjectName("pageHeader")
        h = QtWidgets.QHBoxLayout(heading)
        h.setContentsMargins(16, 11, 16, 11)
        labels = QtWidgets.QVBoxLayout()
        labels.setSpacing(2)
        title = QtWidgets.QLabel("十字路口协同预警")
        title.setObjectName("pageTitle")
        detail = QtWidgets.QLabel("独立的 5 秒协同演示：模拟货车、云端与 ESP32 回执仅用于本页展示，不发送给真实头盔、气泵或 DFPlayer")
        detail.setObjectName("muted")
        detail.setWordWrap(True)
        labels.addWidget(title)
        labels.addWidget(detail)
        h.addLayout(labels, 1)
        self.start_button = QtWidgets.QPushButton("开始 5 秒协同演示")
        self.start_button.setObjectName("primaryAction")
        self.reset_button = QtWidgets.QPushButton("复位")
        self.start_button.clicked.connect(self.begin_demo)
        self.reset_button.clicked.connect(self.reset_demo)
        h.addWidget(self.start_button)
        h.addWidget(self.reset_button)
        root.addWidget(heading)

        content = QtWidgets.QHBoxLayout()
        content.setSpacing(10)
        map_panel = QtWidgets.QFrame()
        map_panel.setObjectName("scenePanel")
        map_layout = QtWidgets.QVBoxLayout(map_panel)
        map_layout.setContentsMargins(12, 10, 12, 12)
        map_head = QtWidgets.QHBoxLayout()
        map_title = QtWidgets.QLabel("路口态势")
        map_title.setObjectName("columnTitle")
        self.map_badge = QtWidgets.QLabel("● 等待演示")
        self.map_badge.setObjectName("softBadge")
        map_head.addWidget(map_title)
        map_head.addStretch(1)
        map_head.addWidget(self.map_badge)
        self.road_map = _CrossroadMap()
        map_layout.addLayout(map_head)
        map_layout.addWidget(self.road_map, 1)
        content.addWidget(map_panel, 2)

        side = QtWidgets.QFrame()
        side.setObjectName("scenePanel")
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.setContentsMargins(14, 12, 14, 12)
        side_layout.setSpacing(9)
        side_title = QtWidgets.QLabel("实时协同链路")
        side_title.setObjectName("columnTitle")
        side_layout.addWidget(side_title)
        eta_card = QtWidgets.QFrame()
        eta_card.setObjectName("etaCard")
        eta_layout = QtWidgets.QVBoxLayout(eta_card)
        eta_layout.setContentsMargins(14, 12, 14, 12)
        eta_caption = QtWidgets.QLabel("货车预计到达路口")
        eta_caption.setObjectName("metricTitle")
        self.eta_value = QtWidgets.QLabel("5.0 秒")
        self.eta_value.setObjectName("etaValue")
        self.deadline_value = QtWidgets.QLabel("ESP32 必须在倒计时结束前响应")
        self.deadline_value.setObjectName("muted")
        self.deadline_value.setWordWrap(True)
        eta_layout.addWidget(eta_caption)
        eta_layout.addWidget(self.eta_value)
        eta_layout.addWidget(self.deadline_value)
        side_layout.addWidget(eta_card)
        self.detection_value = self._info_card("摄像头检测", "等待检测")
        self.cloud_status = self._info_card("云端预测", "等待上传")
        self.helmet_status = self._info_card("头盔 ESP32", "等待下发")
        self.rider_status = self._info_card("骑行者响应", "正常骑行 · 18 km/h")
        self.protection_status = self._info_card("提示与保护动作", "等待 ESP32 确认")
        side_layout.addWidget(self.detection_value[0])
        side_layout.addWidget(self.cloud_status[0])
        side_layout.addWidget(self.helmet_status[0])
        side_layout.addWidget(self.rider_status[0])
        side_layout.addWidget(self.protection_status[0])
        side_layout.addStretch(1)
        self.event_value = self._value("事件 ID · 等待演示")
        self.network_value = self._value("网络耗时 · —")
        self.rgb_value = self._value("RGB · 等待 ACK")
        self.voice_value = self._value("语音 · 等待真实反馈")
        self.serial_status = self._value("串口状态 · 等待")
        for value in (self.event_value, self.network_value, self.rgb_value, self.voice_value, self.serial_status):
            value.setWordWrap(True)
            side_layout.addWidget(value)
        content.addWidget(side, 1)
        root.addLayout(content, 1)

        stages = QtWidgets.QHBoxLayout()
        stages.setSpacing(7)
        self.stages = [
            _ScenarioStage(1, "监控发现"), _ScenarioStage(2, "上传云端"),
            _ScenarioStage(3, "云端预测"), _ScenarioStage(4, "下发头盔"),
            _ScenarioStage(5, "ESP32 响应"),
        ]
        for stage in self.stages:
            stages.addWidget(stage, 1)
        root.addLayout(stages)
        self._reset_state(emit_signal=False)

    @staticmethod
    def _info_card(title: str, initial: str) -> tuple[QtWidgets.QFrame, QtWidgets.QLabel]:
        card = QtWidgets.QFrame()
        card.setObjectName("scenarioInfoCard")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(11, 8, 11, 8)
        layout.setSpacing(3)
        caption = QtWidgets.QLabel(title)
        caption.setObjectName("metricTitle")
        value = QtWidgets.QLabel(initial)
        value.setObjectName("mappingValue")
        value.setWordWrap(True)
        layout.addWidget(caption)
        layout.addWidget(value)
        return card, value

    @staticmethod
    def _value(text: str) -> QtWidgets.QLabel:
        value = QtWidgets.QLabel(text)
        value.setObjectName("monoMuted")
        return value

    def set_reduced_motion(self, enabled: bool) -> None:
        self._reduced_motion = enabled
        self.road_map.reduced_motion = enabled
        self._timer.setInterval(160 if enabled else 33)

    def demo_payload(self, eta_ms: int | None = None) -> dict:
        remaining = max(0, self.EVENT_DURATION_MS - self._last_elapsed_ms) if eta_ms is None else max(0, eta_ms)
        return {
            "event_id": self.current_event_id, "device_id": "aix-helmet-01", "camera_id": "roadside-cam-01",
            "intersection_id": "demo-crossing-01", "direction": "right", "object_type": "truck",
            "eta_ms": remaining, "severity": "high", "ttl_ms": 7000, "simulated": True,
            "message_code": "truck_right_eta_5s",
        }

    def begin_demo(self) -> None:
        if self._running:
            return
        self.current_event_id = f"roadside-truck-{uuid.uuid4().hex[:10]}"
        self._running = True
        self._dispatched = False
        self._ack_received = False
        self._ack_remaining_ms = None
        self._ack_elapsed_ms = None
        self._ack_is_simulated = False
        self._last_elapsed_ms = 0
        self._clock.start()
        self.start_button.setEnabled(False)
        self.event_value.setText(f"事件 ID · {self.current_event_id}")
        self._update_from_elapsed(0)
        self._timer.start()

    def reset_demo(self) -> None:
        self._reset_state(emit_signal=True)

    def _reset_state(self, *, emit_signal: bool) -> None:
        self._timer.stop()
        self._running = False
        self._dispatched = False
        self._ack_received = False
        self._ack_remaining_ms = None
        self._ack_elapsed_ms = None
        self._ack_is_simulated = False
        self.current_event_id = ""
        self._last_elapsed_ms = 0
        self.start_button.setEnabled(True)
        for stage in self.stages:
            stage.set_state("等待", "waiting")
        self.eta_value.setText("5.0 秒")
        self.deadline_value.setText("ESP32 必须在倒计时结束前响应")
        self.event_value.setText("事件 ID · 等待演示")
        self.network_value.setText("网络耗时 · —")
        self.rgb_value.setText("RGB · 等待 ACK")
        self.voice_value.setText("语音 · 等待真实反馈")
        self.serial_status.setText("串口状态 · 等待")
        self.detection_value[1].setText("等待检测")
        self.cloud_status[1].setText("等待上传")
        self.helmet_status[1].setText("等待下发")
        self.rider_status[1].setText("正常骑行 · 18 km/h")
        self.protection_status[1].setText("等待 ESP32 确认")
        self.map_badge.setText("● 等待演示")
        self.road_map.set_state(0.0, 5.0, "等待演示")
        if emit_signal:
            self.reset_requested.emit()

    def _tick(self) -> None:
        if self._running:
            self._update_from_elapsed(self._clock.elapsed())

    def _update_from_elapsed(self, elapsed_ms: int) -> None:
        """Authoritative timeline entry point; tests can drive it without sleeping."""
        if not self._running:
            return
        elapsed_ms = max(0, int(elapsed_ms))
        self._last_elapsed_ms = elapsed_ms
        remaining_ms = max(0, self.EVENT_DURATION_MS - elapsed_ms)
        eta = remaining_ms / 1000.0
        progress = min(1.0, elapsed_ms / self.EVENT_DURATION_MS)

        if elapsed_ms < 260:
            phase = "路侧摄像头锁定右侧货车"
            self.stages[0].set_state("货车 · 置信度 0.94", "active")
            self.detection_value[1].setText("货车 · 右侧来向 · 置信度 0.94")
            self.map_badge.setText("● 已发现货车")
        elif elapsed_ms < 560:
            phase = "检测结果正在上传云端"
            self.stages[0].set_state("检测完成 · 0.94", "completed")
            self.stages[1].set_state("正在上传检测事件", "active")
            self.cloud_status[1].setText("正在上传目标、方向和 ETA 数据")
        elif elapsed_ms < self.CLOUD_DISPATCH_MS:
            phase = "云端正在预测到达时间"
            self.stages[0].set_state("检测完成 · 0.94", "completed")
            self.stages[1].set_state("上传完成", "completed")
            self.stages[2].set_state(f"预测 ETA {eta:.1f} 秒", "active")
            self.cloud_status[1].setText(f"货车预计 {eta:.1f} 秒后到达路口")
        else:
            phase = "预警已下发，等待 ESP32 在期限前响应"
            self.stages[0].set_state("检测完成 · 0.94", "completed")
            self.stages[1].set_state("上传完成", "completed")
            self.stages[2].set_state(f"ETA 持续更新 · {eta:.1f} 秒", "completed")
            self.cloud_status[1].setText(f"预测完成 · 货车约 {eta:.1f} 秒后到达")
            if not self._dispatched:
                self._dispatched = True
                # Keep the restored demonstration self-contained: it must never
                # inject its historical simulated=true event into the real chain.
                self._accept_response(elapsed_ms, simulated=True)
                self.stages[3].set_state("演示下发完成", "completed")
                self.helmet_status[1].setText("本地演示回执 · 未向真实 ESP32 下发")
                self.voice_value.setText("语音 · 演示提示（不播放硬件）")
            if not self._ack_received:
                self.stages[4].set_state(f"等待响应 · 剩余 {eta:.1f} 秒", "waiting")

        # 骑行者先按正常速度接近路口；只有真实 ACK 才改变演示结果。
        rider_progress = min(0.82, progress * 0.82)
        rider_slowed = False
        rider_speed_kmh = 18
        if self._ack_received and self._ack_elapsed_ms is not None:
            after_ack_ms = max(0, elapsed_ms - self._ack_elapsed_ms)
            base_progress = min(0.82, self._ack_elapsed_ms / self.EVENT_DURATION_MS * 0.82)
            rider_progress = min(0.92, base_progress + max(0, after_ack_ms - 700) / self.EVENT_DURATION_MS * 0.10)
            if after_ack_ms < 700:
                phase = "ESP32 已确认，等待真实执行反馈"
                self.rider_status[1].setText("收到预警 · 准备减速")
                self.protection_status[1].setText("等待真实 DFPlayer 与泵阀状态")
            else:
                phase = "预警已确认，模拟骑行者减速通过路口"
                rider_slowed = True
                rider_speed_kmh = 6
                self.rider_status[1].setText("模拟减速 · 6 km/h · 保持安全距离")
                self.map_badge.setText("● 真实 ACK 已确认")
        else:
            self.rider_status[1].setText("正常骑行 · 18 km/h")
            self.protection_status[1].setText("等待 ESP32 确认")

        self.eta_value.setText(f"{eta:.1f} 秒")
        self.road_map.set_state(
            progress, eta, phase,
            rider_progress=rider_progress,
            rider_slowed=rider_slowed,
            rider_speed_kmh=rider_speed_kmh,
        )
        if remaining_ms <= 0:
            self._running = False
            self._timer.stop()
            if self._ack_received:
                source = "演示链路" if self._ack_is_simulated else "ESP32"
                self.deadline_value.setText(f"{source} 已提前 {self._ack_remaining_ms / 1000.0:.1f} 秒完成响应")
            else:
                self.stages[4].set_state("响应超时 · 未在货车到达前确认", "failed")
                self.helmet_status[1].setText("响应超时：未收到有效 ESP32 ACK")
                self.deadline_value.setText("货车已到达路口，当前演示响应失败")
                self.map_badge.setText("● 响应超时")

    def apply_chain_state(self, state: dict) -> None:
        hazard = state.get("road_hazard") if isinstance(state, dict) else None
        if not isinstance(hazard, dict) or not hazard.get("event_id"):
            return
        event_id = str(hazard.get("event_id"))
        if self.current_event_id and event_id != self.current_event_id:
            return
        if not self.current_event_id:
            self.current_event_id = event_id
        self.event_value.setText(f"事件 ID · {event_id}")
        delivery = hazard.get("delivery", {}) if isinstance(hazard.get("delivery"), dict) else {}
        attempts = int(hazard.get("attempts", 0) or 0)
        delivery_state = str(delivery.get("state", "waiting"))
        if delivery_state == "completed":
            self.stages[3].set_state("下发完成", "completed")
            self.helmet_status[1].setText("命令已下发，等待 ESP32 返回有效 ACK")
        elif delivery_state == "failed":
            self.stages[3].set_state(f"下发失败 · 已重试 {attempts} 次", "failed")
            self.helmet_status[1].setText(str(hazard.get("error") or "下发失败，ESP32 可能离线"))
        elif delivery_state == "active":
            self.stages[3].set_state(f"下发中 · 第 {attempts + 1} 次", "active")

        ack = hazard.get("ack", {}) if isinstance(hazard.get("ack"), dict) else {}
        payload = ack.get("payload") if isinstance(ack, dict) else None
        real_ack = (
            isinstance(payload, dict) and payload.get("type") == "road_hazard_ack"
            and payload.get("accepted") is True and payload.get("event_id") == event_id
        )
        elapsed = max(
            self._last_elapsed_ms,
            self._clock.elapsed() if self._running and self._clock.isValid() else 0,
        )
        if real_ack and elapsed < self.EVENT_DURATION_MS:
            self._accept_response(elapsed, simulated=False)
            voice_state = str(payload.get("voice_state") or "not_requested")
            self.voice_value.setText(f"语音 · {voice_state}")
        elif real_ack:
            self.stages[4].set_state("收到 ACK，但已超过到达期限", "failed")
            self.helmet_status[1].setText("响应超时：ACK 晚于货车到达时间")
        elif delivery_state == "failed" or ack.get("state") == "failed":
            self.stages[4].set_state("未确认 · ESP32 离线或拒绝", "failed")
        latency = hazard.get("network_latency_ms")
        self.network_value.setText(f"网络耗时 · {int(latency)} 毫秒" if isinstance(latency, (int, float)) else "网络耗时 · —")
        pattern = str(hazard.get("effective_rgb_pattern") or "")
        self.rgb_value.setText(f"RGB · {pattern}" if pattern else "RGB · 等待 ACK")

    def apply_submission_error(self, message: str) -> None:
        """Expose real cloud/service rejection instead of leaving a simulated success state."""
        if not self.current_event_id:
            return
        self.stages[3].set_state("下发失败 · 协同服务拒绝", "failed")
        self.stages[4].set_state("未确认 · 未到达 ESP32", "failed")
        self.helmet_status[1].setText(message or "协同服务拒绝预警事件")
        self.deadline_value.setText("下发失败；倒计时继续，仅用于观察货车到达过程")
        self.map_badge.setText("● 下发失败")

    def _accept_response(self, elapsed_ms: int, *, simulated: bool) -> None:
        """Record a response; production flow only calls this for a real ESP32 ACK."""
        self._ack_received = True
        self._ack_is_simulated = simulated
        self._ack_remaining_ms = self.EVENT_DURATION_MS - elapsed_ms
        self._ack_elapsed_ms = elapsed_ms
        remaining = self._ack_remaining_ms / 1000.0
        self.stages[3].set_state("下发完成", "completed")
        if simulated:
            self.stages[4].set_state(f"演示响应 · 提前 {remaining:.1f} 秒", "completed")
            self.helmet_status[1].setText(f"演示 ACK 已确认 · 剩余安全时间 {remaining:.1f} 秒")
            self.deadline_value.setText(f"演示链路已在期限前响应，剩余 {remaining:.1f} 秒")
            self.map_badge.setText("● 演示响应已确认")
        else:
            self.stages[4].set_state(f"真实 ACK · 提前 {remaining:.1f} 秒", "completed")
            self.helmet_status[1].setText(f"ESP32 已响应 · 剩余安全时间 {remaining:.1f} 秒")
            self.deadline_value.setText(f"ESP32 已在期限前响应，剩余 {remaining:.1f} 秒")
            self.map_badge.setText("● ESP32 已响应")

    def apply_serial_status(self, event) -> None:
        self.serial_status.setText(f"串口状态 · {event.state} · {event.event_id or '—'}")
        if event.effective_rgb_pattern:
            self.rgb_value.setText(f"RGB · {event.effective_rgb_pattern}")

    def apply_voice_status(self, event) -> None:
        """Real DFPlayer feedback takes precedence over the illustrative timeline."""
        state = str(event.state or "unknown")
        track = f" · 曲目 {event.track}" if getattr(event, "track", None) is not None else ""
        self.voice_value.setText(f"语音 · {state}{track}")
        if state in {"playing", "completed", "done"}:
            self.protection_status[1].setText("收到真实 DFPlayer 反馈")

    def apply_pneumatic_status(self, event) -> None:
        """Surface true pump/valve telemetry without pretending an animation is hardware proof."""
        if bool(getattr(event, "self_test_failed", False)):
            self.protection_status[1].setText("气动自检失败 · 压力未上升 · 自动充气已锁止")
            return
        pump = "开" if bool(getattr(event, "pump_on", False)) else "关"
        valve = "开" if bool(getattr(event, "valve_on", False)) else "关"
        state = str(getattr(event, "state", "未知"))
        self.protection_status[1].setText(f"真实气动反馈 · {state} · 泵 {pump} / 阀 {valve}")
