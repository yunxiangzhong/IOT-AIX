from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class ClickableStatusCard(QtWidgets.QFrame):
    """Compact, keyboard-accessible status card used by the dashboard."""

    clicked = QtCore.Signal(str)

    _ICON_STATES = {
        "ok": QtWidgets.QStyle.StandardPixmap.SP_DialogApplyButton,
        "info": QtWidgets.QStyle.StandardPixmap.SP_MessageBoxInformation,
        "attention": QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning,
        "high": QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical,
        "critical": QtWidgets.QStyle.StandardPixmap.SP_MessageBoxCritical,
        "fault": QtWidgets.QStyle.StandardPixmap.SP_DialogCancelButton,
        "muted": QtWidgets.QStyle.StandardPixmap.SP_MessageBoxInformation,
    }

    def __init__(self, metric_key: str, title: str, parent=None) -> None:
        super().__init__(parent)
        self.metric_key = metric_key
        self.setObjectName("clickableStatusCard")
        self.setProperty("statusTone", "")
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(64)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Expanding)
        self.setAccessibleName(f"{title}状态卡")
        self.setAccessibleDescription("按 Enter 或点击查看趋势")

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(9, 8, 9, 8)
        layout.setSpacing(3)
        heading = QtWidgets.QHBoxLayout()
        heading.setSpacing(5)
        self.icon = QtWidgets.QLabel()
        self.icon.setObjectName("metricStatusIcon")
        self.icon.setFixedSize(20, 20)
        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("mappingLabel")
        self.title_label.setWordWrap(True)
        heading.addWidget(self.icon)
        heading.addWidget(self.title_label, 1)
        self.value_label = QtWidgets.QLabel("等待")
        self.value_label.setObjectName("mappingValue")
        self.value_label.setMinimumHeight(16)
        self.value_label.setWordWrap(True)
        self.value_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.secondary_label = QtWidgets.QLabel()
        self.secondary_label.setObjectName("mappingValue")
        self.secondary_label.setWordWrap(True)
        self.secondary_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        self.hint_label = QtWidgets.QLabel("查看趋势")
        self.hint_label.setObjectName("metricTrendHint")
        self.hint_label.hide()
        layout.addLayout(heading)
        layout.addWidget(self.value_label, 1)
        layout.addWidget(self.secondary_label)
        layout.addWidget(self.hint_label)
        self._raw_value = "等待"
        self.set_status("muted", "等待")

    def set_value(self, value: str) -> None:
        value = str(value)
        if value == self._raw_value:
            return
        self._raw_value = value
        lines = value.splitlines() or [""]
        # The first line is the numeric/live line for motion and pressure;
        # camera/risk cards keep their stable subject/status line first.
        dynamic_index = 1 if self.metric_key == "ov5640" and len(lines) > 1 else 0
        dynamic = lines[dynamic_index]
        static = "\n".join(lines[:dynamic_index] + lines[dynamic_index + 1:])
        if self.value_label.text() != dynamic:
            self.value_label.setText(dynamic)
        if self.secondary_label.text() != static:
            self.secondary_label.setText(static)
        self.secondary_label.setVisible(bool(static))

    def set_status(self, tone: str, value: str | None = None) -> None:
        if value is not None:
            self.set_value(value)
        if self.property("statusTone") == tone:
            return
        self.setProperty("statusTone", tone)
        standard_pixmap = self._ICON_STATES.get(tone, self._ICON_STATES["muted"])
        pixmap = self.style().standardPixmap(standard_pixmap)
        self.icon.setPixmap(pixmap.scaled(18, 18, QtCore.Qt.AspectRatioMode.KeepAspectRatio, QtCore.Qt.TransformationMode.SmoothTransformation))
        self.style().unpolish(self)
        self.style().polish(self)

    def set_trend_enabled(self, enabled: bool) -> None:
        self.setProperty("trendEnabled", bool(enabled))
        self.hint_label.setVisible(bool(enabled))
        self.setCursor(QtCore.Qt.CursorShape.PointingHandCursor if enabled else QtCore.Qt.CursorShape.ArrowCursor)
        self.setAccessibleDescription("按 Enter 或点击查看趋势" if enabled else "状态信息")
        self.style().unpolish(self)
        self.style().polish(self)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # noqa: N802
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self.property("trendEnabled"):
            self.clicked.emit(self.metric_key)
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # noqa: N802
        if event.key() in (QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter, QtCore.Qt.Key.Key_Space):
            if self.property("trendEnabled"):
                self.clicked.emit(self.metric_key)
                event.accept()
                return
        super().keyPressEvent(event)
