from __future__ import annotations

from PySide6 import QtWidgets


class EventTimeline(QtWidgets.QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")

        self.summary = QtWidgets.QLabel("等待数据")
        self.summary.setObjectName("muted")
        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(300)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 18)
        layout.setSpacing(10)

        header = QtWidgets.QHBoxLayout()
        title = QtWidgets.QLabel("事件流")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(self.summary)
        layout.addLayout(header)
        layout.addWidget(self.log)

    def add_line(self, line: str) -> None:
        self.log.appendPlainText(line)

    def set_summary(self, text: str) -> None:
        self.summary.setText(text)
