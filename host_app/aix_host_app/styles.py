from __future__ import annotations


def app_stylesheet() -> str:
    return """
    QWidget {
        background: #eef4f0;
        color: #25302d;
        font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
        font-size: 13px;
    }
    QMainWindow {
        background: #eef4f0;
    }
    QFrame#panel {
        background: #f8fbf8;
        border: 1px solid #d8e3dc;
        border-radius: 8px;
    }
    QLabel#sectionTitle {
        color: #1e2c29;
        font-size: 16px;
        font-weight: 700;
        background: transparent;
    }
    QLabel#metricValue {
        color: #0f766e;
        font-size: 38px;
        font-weight: 800;
        background: transparent;
    }
    QFrame#metricCell {
        background: #ffffff;
        border: 1px solid #d7e4dd;
        border-radius: 6px;
    }
    QLabel#metricTitle {
        color: #687873;
        font-size: 12px;
        font-weight: 700;
        background: transparent;
    }
    QLabel#metricCellValue {
        color: #16352f;
        font-size: 22px;
        font-weight: 800;
        background: transparent;
    }
    QLabel#metricSmallValue {
        color: #0f766e;
        font-size: 24px;
        font-weight: 800;
        background: transparent;
    }    QLabel#muted {
        color: #687873;
        background: transparent;
    }
    QLabel#statusOk {
        color: #0f766e;
        font-weight: 700;
        background: transparent;
    }
    QLabel#statusWarn {
        color: #b45309;
        font-weight: 700;
        background: transparent;
    }
    QLabel#statusDanger {
        color: #b91c1c;
        font-weight: 700;
        background: transparent;
    }
    QPushButton, QToolButton {
        background: #243b35;
        border: 1px solid #243b35;
        border-radius: 6px;
        color: #f8fbf8;
        min-height: 30px;
        padding: 5px 10px;
    }
    QPushButton:hover, QToolButton:hover {
        background: #315149;
        border-color: #315149;
    }
    QPushButton:disabled, QToolButton:disabled {
        background: #c6d2cb;
        border-color: #c6d2cb;
        color: #73847d;
    }
    QToolButton#followButton {
        background: #f8fbf8;
        border: 1px solid #8fb0a7;
        border-radius: 6px;
        color: #0f766e;
        min-height: 28px;
        padding: 4px 10px;
    }
    QToolButton#followButton:checked {
        background: #0f766e;
        border-color: #0f766e;
        color: #f8fbf8;
    }
    QComboBox, QSpinBox, QLineEdit {
        background: #ffffff;
        border: 1px solid #ccd8d1;
        border-radius: 6px;
        min-height: 30px;
        padding: 3px 8px;
    }
    QCheckBox {
        background: transparent;
        spacing: 8px;
    }
    QPlainTextEdit, QTextEdit {
        background: #101816;
        border: 1px solid #243b35;
        border-radius: 8px;
        color: #d7efe8;
        font-family: "Cascadia Mono", "Consolas", monospace;
        font-size: 12px;
        padding: 8px;
    }
    QSplitter::handle {
        background: #d7e4dd;
    }
    """
