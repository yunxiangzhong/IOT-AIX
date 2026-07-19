from __future__ import annotations

from copy import deepcopy

from PySide6 import QtCore, QtGui, QtWidgets


CLASS_LABELS = {
    "person": "行人",
    "bicycle": "自行车",
    "car": "汽车",
    "motorcycle": "摩托车",
    "bus": "公交车",
    "truck": "卡车",
    "traffic light": "交通灯",
    "stop sign": "停止标志",
}


class VisionCanvas(QtWidgets.QWidget):
    """Stable letterboxed image canvas with lightweight detection overlays."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._image = QtGui.QImage()
        self._detections: list[dict] = []
        self.setObjectName("activeCamera")
        self.setMinimumSize(480, 270)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.setAccessibleName("已分析交通视觉画面")

    @property
    def detections(self) -> tuple[dict, ...]:
        return tuple(deepcopy(self._detections))

    def sizeHint(self) -> QtCore.QSize:  # noqa: N802 - Qt API
        return QtCore.QSize(640, 360)

    def minimumSizeHint(self) -> QtCore.QSize:  # noqa: N802 - Qt API
        return QtCore.QSize(480, 270)

    def set_snapshot(self, image_data: bytes, detections: list[dict]) -> bool:
        image = QtGui.QImage.fromData(image_data)
        if image.isNull():
            return False
        self._image = image
        self._detections = deepcopy(detections) if isinstance(detections, list) else []
        self.setAccessibleDescription(f"已分析画面，检测到 {len(self._detections)} 个交通目标")
        self.update()
        return True

    @staticmethod
    def _box_color(detection: dict) -> QtGui.QColor:
        risk = float(detection.get("risk_score", 0) or 0)
        if risk >= 80:
            return QtGui.QColor("#F87171")
        if risk >= 60:
            return QtGui.QColor("#FB923C")
        if risk >= 30:
            return QtGui.QColor("#FBBF24")
        return QtGui.QColor("#34D399")

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt API
        super().paintEvent(event)
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QtGui.QColor("#02070D"))
        if self._image.isNull():
            painter.setPen(QtGui.QColor("#718096"))
            painter.drawText(self.rect(), QtCore.Qt.AlignmentFlag.AlignCenter, "等待已分析画面")
            return

        scale = min(self.width() / self._image.width(), self.height() / self._image.height())
        draw_width = self._image.width() * scale
        draw_height = self._image.height() * scale
        target = QtCore.QRectF(
            (self.width() - draw_width) / 2.0,
            (self.height() - draw_height) / 2.0,
            draw_width,
            draw_height,
        )
        painter.drawImage(target, self._image)

        font = QtGui.QFont(QtWidgets.QApplication.font())
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        metrics = QtGui.QFontMetrics(font)
        for detection in self._detections:
            try:
                left, top, right, bottom = (float(value) for value in detection["bbox_norm"])
            except (KeyError, TypeError, ValueError):
                continue
            if right <= left or bottom <= top:
                continue
            box = QtCore.QRectF(
                target.left() + max(0.0, min(1.0, left)) * target.width(),
                target.top() + max(0.0, min(1.0, top)) * target.height(),
                max(0.0, min(1.0, right) - max(0.0, min(1.0, left))) * target.width(),
                max(0.0, min(1.0, bottom) - max(0.0, min(1.0, top))) * target.height(),
            )
            color = self._box_color(detection)
            painter.setPen(QtGui.QPen(color, 2.0))
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box, 3, 3)
            class_name = str(detection.get("class_name") or "目标")
            label = CLASS_LABELS.get(class_name, class_name)
            confidence = float(detection.get("score", 0) or 0)
            label = f"{label} {confidence:.0%}"
            label_width = metrics.horizontalAdvance(label) + 12
            label_height = metrics.height() + 6
            label_top = max(target.top(), box.top() - label_height)
            label_rect = QtCore.QRectF(box.left(), label_top, label_width, label_height)
            background = QtGui.QColor(color)
            background.setAlpha(220)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(background)
            painter.drawRoundedRect(label_rect, 3, 3)
            painter.setPen(QtGui.QColor("#07111F"))
            painter.drawText(label_rect.adjusted(6, 2, -6, -2), QtCore.Qt.AlignmentFlag.AlignVCenter, label)
