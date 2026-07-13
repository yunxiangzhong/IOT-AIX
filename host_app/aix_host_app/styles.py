from __future__ import annotations


def app_stylesheet() -> str:
    return """
    QWidget {
        background: #F6F6F4;
        color: #20201E;
        font-family: "Segoe UI Variable Text", "Microsoft YaHei UI", "SF Pro Text", sans-serif;
        font-size: 12px;
    }
    QMainWindow {
        background: #F6F6F4;
    }
    QFrame#panel {
        background: #FCFCFB;
        border: 1px solid #E2E2DE;
        border-radius: 8px;
    }
    QFrame#cameraPreview {
        background: #F1EFE9;
        border: 1px solid #E2DED2;
        border-radius: 7px;
    }
    QLabel#cameraPreviewImage {
        background: #242522;
        color: #E6E4DD;
        border-radius: 4px;
        font-size: 12px;
    }
    QLabel#sectionTitle {
        color: #20201E;
        font-size: 13px;
        font-weight: 600;
        background: transparent;
    }
    QLabel#metricValue {
        color: #20201E;
        font-family: "SF Mono", "Consolas", monospace;
        font-size: 28px;
        font-weight: 600;
        background: transparent;
    }
    QFrame#metricCell {
        background: transparent;
        border: none;
    }
    QLabel#metricTitle {
        color: #6F6F6B;
        font-size: 11px;
        font-weight: 600;
        background: transparent;
    }
    QLabel#metricCellValue {
        color: #20201E;
        font-family: "SF Mono", "Consolas", monospace;
        font-size: 20px;
        font-weight: 600;
        background: transparent;
    }
    QLabel#metricSmallValue {
        color: #20201E;
        font-family: "SF Mono", "Consolas", monospace;
        font-size: 18px;
        font-weight: 600;
        background: transparent;
    }
    QLabel#muted {
        color: #6F6F6B;
        font-size: 11px;
        background: transparent;
    }
    QLabel#statusOk {
        color: #2B6E4B;
        font-weight: 600;
        background: transparent;
    }
    QLabel#statusWarn {
        color: #B87B2E;
        font-weight: 600;
        background: transparent;
    }
    QLabel#statusDanger {
        color: #B83E3E;
        font-weight: 600;
        background: transparent;
    }
    QPushButton, QToolButton {
        background: #FCFCFB;
        border: 1px solid #E2E2DE;
        border-radius: 6px;
        color: #20201E;
        font-weight: 500;
        min-height: 28px;
        padding: 4px 12px;
    }
    QPushButton:hover, QToolButton:hover {
        background: #F1F1EF;
        border-color: #D2D2CE;
    }
    QPushButton:pressed, QToolButton:pressed {
        background: #ECECE8;
        border-color: #B5B5B0;
    }
    QPushButton:disabled, QToolButton:disabled {
        background: #F1F1EF;
        border-color: #ECECE8;
        color: #9A9A95;
    }
    
    /* Primary buttons styling */
    QPushButton[primary="true"], QToolButton[primary="true"] {
        background: #007AFF;
        border: 1px solid #007AFF;
        color: #FCFCFB;
    }
    QPushButton[primary="true"]:hover, QToolButton[primary="true"]:hover {
        background: #268DFF;
        border-color: #268DFF;
    }
    QPushButton[primary="true"]:pressed, QToolButton[primary="true"]:pressed {
        background: #0066D6;
        border-color: #0066D6;
    }
    QPushButton[primary="true"]:disabled, QToolButton[primary="true"]:disabled {
        background: #F1F1EF;
        border-color: #ECECE8;
        color: #9A9A95;
    }
    
    QToolButton#followButton {
        background: #FCFCFB;
        border: 1px solid #E2E2DE;
        border-radius: 6px;
        color: #6F6F6B;
        min-height: 24px;
        padding: 3px 8px;
        font-size: 11px;
    }
    QToolButton#followButton:checked {
        background: #007AFF;
        border-color: #007AFF;
        color: #FCFCFB;
    }
    QComboBox, QSpinBox, QLineEdit {
        background: #FCFCFB;
        border: 1px solid #E2E2DE;
        border-radius: 6px;
        color: #20201E;
        min-height: 28px;
        padding: 3px 8px;
    }
    QComboBox:focus, QSpinBox:focus, QLineEdit:focus {
        border: 1px solid #007AFF;
    }
    QComboBox:disabled, QSpinBox:disabled, QLineEdit:disabled {
        background: #F1F1EF;
        color: #9A9A95;
        border-color: #ECECE8;
    }
    QComboBox QAbstractItemView {
        background-color: #FCFCFB;
        color: #20201E;
        border: 1px solid #E2E2DE;
        selection-background-color: #F1F1EF;
        selection-color: #20201E;
    }
    QCheckBox {
        background: transparent;
        spacing: 8px;
    }
    QPlainTextEdit, QTextEdit {
        background: #FBFBFA;
        border: 1px solid #E2E2DE;
        border-radius: 8px;
        color: #20201E;
        font-family: "SF Mono", "Consolas", monospace;
        font-size: 11px;
        padding: 8px;
    }
    QSplitter::handle {
        background: #ECECE8;
    }
    QScrollBar:vertical {
        border: none;
        background: transparent;
        width: 8px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: #D2D2CE;
        min-height: 20px;
        border-radius: 4px;
    }
    QScrollBar::handle:vertical:hover {
        background: #B5B5B0;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    QScrollBar:horizontal {
        border: none;
        background: transparent;
        height: 8px;
        margin: 0px;
    }
    QScrollBar::handle:horizontal {
        background: #D2D2CE;
        min-width: 20px;
        border-radius: 4px;
    }
    QScrollBar::handle:horizontal:hover {
        background: #B5B5B0;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
        width: 0px;
    }
    QStatusBar {
        background: #F6F6F4;
        color: #6F6F6B;
        border-top: 1px solid #E2E2DE;
    }
    """
