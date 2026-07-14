from __future__ import annotations


def app_stylesheet() -> str:
    return """
    QWidget {
        background: #F4F3EF;
        color: #20201E;
        font-family: "Microsoft YaHei UI", "Segoe UI Variable", "Segoe UI", sans-serif;
        font-size: 12px;
    }
    QMainWindow, QWidget#activeDashboard { background: #F4F3EF; }
    QFrame#instrumentHeader, QFrame#chainBand, QFrame#instrumentPanel, QFrame#metricBand,
    QFrame#panel, QTabWidget#diagnostics::pane {
        background: #FCFBF7;
        border: 1px solid #D8D6CF;
        border-radius: 5px;
    }
    QFrame#instrumentHeader { border-radius: 4px; }
    QLabel#instrumentTitle {
        background: transparent;
        font-size: 17px;
        font-weight: 650;
        letter-spacing: 1px;
    }
    QLabel#instrumentSubtitle, QLabel#metricTitle {
        background: transparent;
        color: #6F6E68;
        font-size: 10px;
        font-weight: 650;
        letter-spacing: 1px;
    }
    QLabel#headerTelemetry {
        background: transparent;
        border-left: 1px solid #D8D6CF;
        color: #20201E;
        font-family: Consolas, "Cascadia Mono", monospace;
        padding: 7px 18px;
    }
    QFrame#chainStage {
        background: #FCFBF7;
        border: none;
        border-right: 1px solid #D8D6CF;
        border-radius: 0;
    }
    QLabel#stageTitle { background: transparent; font-size: 12px; font-weight: 650; }
    QLabel#stageDot { background: transparent; font-size: 11px; }
    QLabel#monoMuted, QLabel#metricMono {
        background: transparent;
        color: #6F6E68;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 10px;
    }
    QFrame#panelHead {
        background: #FCFBF7;
        border: none;
        border-bottom: 1px solid #D8D6CF;
    }
    QLabel#activeCamera {
        background: #DDDCD7;
        color: #6F6E68;
        border: none;
        font-family: Consolas, monospace;
    }
    QLabel#riskScore {
        background: transparent;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 46px;
        font-weight: 700;
    }
    QLabel#riskBand, QLabel#actionName {
        background: transparent;
        font-size: 18px;
        font-weight: 650;
    }
    QLabel#muted { background: transparent; color: #6F6E68; line-height: 1.5; }
    QFrame#bottomMetric, QFrame#metricCell {
        background: #FCFBF7;
        border: none;
        border-right: 1px solid #D8D6CF;
        border-radius: 0;
    }
    QLabel#metricMono, QLabel#metricCellValue, QLabel#metricSmallValue, QLabel#metricValue {
        background: transparent;
        color: #20201E;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 13px;
        font-weight: 600;
    }
    QPushButton, QToolButton {
        background: #FCFBF7;
        border: 1px solid #D8D6CF;
        border-radius: 4px;
        min-height: 28px;
        padding: 3px 11px;
    }
    QPushButton:hover, QToolButton:hover { background: #F0EFEA; border-color: #AAA8A1; }
    QPushButton:checked, QToolButton:checked {
        background: #20201E;
        color: #FCFBF7;
        border-color: #20201E;
    }
    QComboBox, QSpinBox, QLineEdit {
        background: #FCFBF7;
        border: 1px solid #D8D6CF;
        border-radius: 4px;
        min-height: 28px;
        padding: 3px 8px;
    }
    QComboBox:focus, QSpinBox:focus, QLineEdit:focus { border-color: #20201E; }
    QPlainTextEdit, QTextEdit {
        background: #FCFBF7;
        color: #20201E;
        border: none;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 10px;
        padding: 8px;
    }
    QTabWidget#diagnostics QTabBar::tab {
        background: #F0EFEA;
        border: 1px solid #D8D6CF;
        border-bottom: none;
        min-width: 76px;
        padding: 6px 12px;
    }
    QTabWidget#diagnostics QTabBar::tab:selected { background: #FCFBF7; color: #20201E; }
    QSplitter::handle { background: #D8D6CF; width: 1px; }
    QLabel#statusOk { color: #2E704B; font-weight: 650; background: transparent; }
    QLabel#statusWarn { color: #A46B12; font-weight: 650; background: transparent; }
    QLabel#statusDanger { color: #A72F2F; font-weight: 650; background: transparent; }
    QStatusBar { background: #F4F3EF; color: #6F6E68; border-top: 1px solid #D8D6CF; }
    QScrollBar:vertical { background: transparent; width: 8px; }
    QScrollBar::handle:vertical { background: #C4C2BB; min-height: 24px; border-radius: 4px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """
