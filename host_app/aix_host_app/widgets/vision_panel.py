from __future__ import annotations

import time

from PySide6 import QtCore, QtGui, QtNetwork, QtWidgets

from ..models import CameraPreviewEvent, CameraStatusEvent, VisionDepthEvent
from ..networking import build_get_request


class VisionPanel(QtWidgets.QFrame):
    """OV5640 preview plus PC-side vision result display."""

    frame_received = QtCore.Signal(bytes, int, int)
    preview_endpoint_changed = QtCore.Signal(str)

    CAMERA_STATUS_TIMEOUT_MS = 3000

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self._serial_connected = False
        self.preview_url = ""
        self._preview_reply: QtNetwork.QNetworkReply | None = None
        self._last_preview_image: QtGui.QImage | None = None
        self._last_jpeg = b""
        self._risk_payload: dict | None = None
        self._fallback_seq = 0

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("视觉感知")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)

        self.preview_card = QtWidgets.QFrame()
        self.preview_card.setObjectName("cameraPreview")
        preview_layout = QtWidgets.QVBoxLayout(self.preview_card)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(6)
        self.preview_image_label = QtWidgets.QLabel("等待 Wi-Fi 画面")
        self.preview_image_label.setObjectName("cameraPreviewImage")
        self.preview_image_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview_image_label.setMinimumSize(260, 195)
        self.preview_image_label.setWordWrap(True)
        self.preview_status_label = QtWidgets.QLabel("串口连接后将自动获取画面地址")
        self.preview_status_label.setObjectName("muted")
        preview_layout.addWidget(self.preview_image_label, 1)
        preview_layout.addWidget(self.preview_status_label)
        layout.addWidget(self.preview_card)
        self.overlay_check = QtWidgets.QCheckBox("显示目标框和置信度")
        self.overlay_check.setChecked(True)
        self.overlay_check.toggled.connect(self._render_preview_image)
        layout.addWidget(self.overlay_check)

        self.camera_status_button = QtWidgets.QToolButton()
        self.camera_status_button.setObjectName("muted")
        self.camera_status_button.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.camera_status_button.setText("OV5640：等待状态")
        self.camera_status_button.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.camera_status_button.clicked.connect(self.toggle_camera_details)
        layout.addWidget(self.camera_status_button)

        self.camera_details = QtWidgets.QFrame()
        self.camera_details.setObjectName("cameraDetails")
        details_layout = QtWidgets.QFormLayout(self.camera_details)
        details_layout.setContentsMargins(12, 10, 12, 10)
        details_layout.setSpacing(6)
        self.camera_detail_label = QtWidgets.QLabel("等待 camera_status")
        self.camera_detail_label.setWordWrap(True)
        details_layout.addRow("设备详情", self.camera_detail_label)
        self.camera_details.setVisible(False)
        layout.addWidget(self.camera_details)

        self.detect_label = QtWidgets.QLabel("视觉模型：等待 ESP32-S3 后续接入")
        self.detect_label.setObjectName("muted")
        self.detect_label.setWordWrap(True)
        self.risk_label = QtWidgets.QLabel("PC视觉风险：等待模型")
        self.risk_label.setObjectName("muted")
        self.action_label = QtWidgets.QLabel("气囊策略：模块未接入")
        self.action_label.setObjectName("muted")
        for widget in (self.detect_label, self.risk_label, self.action_label):
            layout.addWidget(widget)

        layout.addStretch(1)

        self.camera_status_timer = QtCore.QTimer(self)
        self.camera_status_timer.setSingleShot(True)
        self.camera_status_timer.setInterval(self.CAMERA_STATUS_TIMEOUT_MS)
        self.camera_status_timer.timeout.connect(self._mark_camera_timeout)
        self.preview_timer = QtCore.QTimer(self)
        self.preview_timer.setInterval(400)
        self.preview_timer.timeout.connect(self._request_preview)
        self.preview_network = QtNetwork.QNetworkAccessManager(self)

    def set_serial_connected(self, connected: bool) -> None:
        self._serial_connected = connected
        self.camera_status_timer.stop()
        if connected:
            self._set_camera_status("OV5640：等待状态", "muted")
            self.camera_status_timer.start()
            self._set_preview_status("等待 ESP32-S3 发布 Wi-Fi 画面地址", "muted")
        else:
            self._set_camera_status("OV5640：等待状态", "muted")
            self.preview_timer.stop()
            self.preview_url = ""
            self._last_jpeg = b""
            self._risk_payload = None
            if self._preview_reply is not None:
                self._preview_reply.abort()
                self._preview_reply = None
            self._set_preview_status("等待串口连接", "muted")
            self.risk_label.setText("PC视觉风险：等待模型")

    def update_camera_preview(self, event: CameraPreviewEvent) -> None:
        if not event.valid:
            self.preview_timer.stop()
            self.preview_url = ""
            self._set_preview_status(f"画面预览不可用：{event.reason}", "statusWarn")
            return
        self.preview_url = event.url
        self.preview_endpoint_changed.emit(event.url)
        self._set_preview_status("Wi-Fi 画面已连接，正在加载…", "statusOk")
        self.preview_timer.start()
        self._request_preview()

    def update_camera_status(self, event: CameraStatusEvent) -> None:
        if not self._serial_connected:
            return

        self.camera_detail_label.setText(
            f"分辨率：{event.width}×{event.height}\n"
            f"格式：{event.pixel_format.upper()}\n"
            f"FPS：{event.fps:.1f}\n"
            f"帧大小：{event.frame_bytes} B\n"
            f"成功帧：{event.frames_ok}\n"
            f"失败次数：{event.capture_failures}\n"
            f"PSRAM：{'已启用' if event.psram else '未启用'}\n"
            f"最后更新：{event.ts_ms} ms"
        )
        if event.valid:
            self._set_camera_status("OV5640：状态正常", "statusOk")
        else:
            self._set_camera_status("OV5640：连接异常", "statusWarn")
        self.camera_status_timer.start()

    def update_vision_depth(self, event: VisionDepthEvent) -> None:
        if event.valid:
            self.detect_label.setText(
                f"视觉模型：{event.model} 相对深度\n"
                f"P10：{event.depth_p10:.3f}  中位数：{event.depth_median:.3f}\n"
                f"置信度：{event.confidence_median:.2f}  推理：{event.latency_ms:.0f} ms"
            )
            self.detect_label.setObjectName("statusOk")
        else:
            self.detect_label.setText(f"视觉模型：{event.model} 返回无效结果")
            self.detect_label.setObjectName("statusWarn")
        self.detect_label.style().unpolish(self.detect_label)
        self.detect_label.style().polish(self.detect_label)

    def update_vision_risk(self, payload: dict) -> None:
        self._risk_payload = payload
        score = int(payload.get("risk_score", 0))
        band = {"low": "低", "attention": "注意", "high": "高", "critical": "严重"}.get(payload.get("risk_band"), "未知")
        object_name = "statusDanger" if score >= 80 else "statusWarn" if score >= 30 else "statusOk"
        self.risk_label.setText(f"PC视觉风险：{score}/100（{band}） | {payload.get('reason', '等待')}")
        self.risk_label.setObjectName(object_name)
        dominant = payload.get("dominant_class") or "无分类目标"
        detections = payload.get("detections") or []
        self.detect_label.setText(
            f"视觉模型：DA3-SMALL + SSDLite\n"
            f"主导目标：{dominant} | 检测数：{len(detections)}\n"
            f"深度中位数：{float(payload.get('depth_median', 0.0)):.3f} | "
            f"置信度：{float(payload.get('confidence_median', 0.0)):.2f} | "
            f"推理：{float(payload.get('latency_ms', 0.0)):.0f} ms"
        )
        self.detect_label.setObjectName("statusOk" if payload.get("valid", False) else "statusWarn")
        for label in (self.risk_label, self.detect_label):
            label.style().unpolish(label)
            label.style().polish(label)
        self._render_preview_image()

    def toggle_camera_details(self) -> None:
        self.camera_details.setVisible(self.camera_details.isHidden())

    def _mark_camera_timeout(self) -> None:
        if self._serial_connected:
            self._set_camera_status("OV5640：连接异常", "statusWarn")

    def _set_camera_status(self, text: str, object_name: str) -> None:
        self.camera_status_button.setText(text)
        self.camera_status_button.setObjectName(object_name)
        self.camera_status_button.style().unpolish(self.camera_status_button)
        self.camera_status_button.style().polish(self.camera_status_button)

    def _request_preview(self) -> None:
        if not self.preview_url or self._preview_reply is not None:
            return
        request = build_get_request(self.preview_url, timeout_ms=4000)
        self._preview_reply = self.preview_network.get(request)
        self._preview_reply.finished.connect(self._handle_preview_reply)

    def _handle_preview_reply(self) -> None:
        reply = self._preview_reply
        self._preview_reply = None
        if reply is None:
            return
        if reply.error() != QtNetwork.QNetworkReply.NetworkError.NoError:
            self._set_preview_status(f"画面读取失败：{reply.errorString()}", "statusWarn")
            reply.deleteLater()
            return
        data = bytes(reply.readAll())
        frame_seq = self._read_header(reply, b"X-Frame-Seq", self._fallback_seq + 1)
        capture_ts_ms = self._read_header(reply, b"X-Capture-Ts-Ms", int(time.time() * 1000))
        self._fallback_seq = frame_seq
        self._last_jpeg = data
        image = QtGui.QImage.fromData(data, "JPG")
        reply.deleteLater()
        if image.isNull():
            self._set_preview_status("画面数据无效，等待下一帧", "statusWarn")
            return
        self._last_preview_image = image
        self.frame_received.emit(data, frame_seq, capture_ts_ms)
        self._render_preview_image()
        self._set_preview_status("Wi-Fi 画面实时更新（2.5 FPS）", "statusOk")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._render_preview_image()

    def _render_preview_image(self) -> None:
        if self._last_preview_image is None:
            return
        image = self._last_preview_image
        if self.overlay_check.isChecked() and self._risk_payload:
            image = self._annotated_image(image, self._risk_payload)
        pixmap = QtGui.QPixmap.fromImage(image).scaled(
            self.preview_image_label.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_image_label.setPixmap(pixmap)

    @staticmethod
    def _read_header(reply: QtNetwork.QNetworkReply, name: bytes | str, fallback: int) -> int:
        try:
            header_name = name.decode("ascii") if isinstance(name, bytes) else name
            value = bytes(reply.rawHeader(header_name)).decode("ascii")
            return int(value)
        except (TypeError, UnicodeDecodeError, ValueError):
            return fallback

    @staticmethod
    def _annotated_image(image: QtGui.QImage, payload: dict) -> QtGui.QImage:
        annotated = image.copy()
        painter = QtGui.QPainter(annotated)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        for detection in payload.get("detections", []):
            left, top, right, bottom = detection.get("bbox_norm", [0, 0, 0, 0])
            rect = QtCore.QRectF(left * image.width(), top * image.height(), (right - left) * image.width(), (bottom - top) * image.height())
            painter.setPen(QtGui.QPen(QtGui.QColor("#FFCC4D"), max(1, image.width() // 160)))
            painter.drawRect(rect)
            painter.drawText(rect.topLeft() + QtCore.QPointF(2, 14), f"{detection.get('class_name', '?')} {float(detection.get('score', 0)):.2f}")
        painter.end()
        return annotated

    def _set_preview_status(self, text: str, object_name: str) -> None:
        self.preview_status_label.setText(text)
        self.preview_status_label.setObjectName(object_name)
        self.preview_status_label.style().unpolish(self.preview_status_label)
        self.preview_status_label.style().polish(self.preview_status_label)
