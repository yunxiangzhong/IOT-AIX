from __future__ import annotations


def app_stylesheet() -> str:
    return """
    QWidget {
        background: #07111F;
        color: #EAF2FB;
        font-family: "Noto Sans SC", "Microsoft YaHei", "Microsoft YaHei UI", "Segoe UI Variable", "Segoe UI", sans-serif;
        font-size: 13px;
    }
    QMainWindow, QWidget#activeDashboard { background: #07111F; }
    QFrame#instrumentHeader, QFrame#visionPanel, QFrame#decisionPanel, QFrame#metricBand,
    QFrame#panel, QTabWidget#diagnostics::pane {
        background: #0D1828;
        border: 1px solid #233249;
        border-radius: 8px;
    }
    QFrame#instrumentHeader { border-radius: 8px; }
    QFrame#chainBand { background: transparent; border: none; }
    QFrame#transparentFrame { background: transparent; border: none; }
    QLabel#instrumentTitle {
        background: transparent;
        color: #F8FBFF;
        font-size: 19px;
        font-weight: 700;
    }
    QLabel#instrumentSubtitle, QLabel#metricTitle {
        background: transparent;
        color: #8FA0B5;
        font-size: 11px;
        font-weight: 600;
    }
    QLabel#headerTelemetry {
        background: transparent;
        border-left: 1px solid #233249;
        color: #C8D4E3;
        padding: 8px 16px;
        font-weight: 550;
    }
    QLabel#systemStatus, QLabel#softBadge {
        background: #0B2940;
        color: #38BDF8;
        border: 1px solid #38BDF8;
        border-radius: 10px;
        padding: 3px 9px;
        font-size: 11px;
        font-weight: 650;
    }
    QFrame#chainStage {
        background: #0D1828;
        border: 1px solid #233249;
        border-radius: 7px;
    }
    QLabel#stageIndex {
        background: #18263A;
        color: #AFC0D4;
        border: 1px solid #304158;
        border-radius: 9px;
        min-width: 18px;
        max-width: 18px;
        min-height: 18px;
        max-height: 18px;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 9px;
        font-weight: 700;
    }
    QLabel#stageTitle { background: transparent; color: #EAF2FB; font-size: 13px; font-weight: 650; }
    QLabel#stageDot { background: transparent; font-size: 10px; }
    QLabel#monoMuted, QLabel#metricMono {
        background: transparent;
        color: #8FA0B5;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 11px;
    }
    QFrame#panelHead {
        background: #111E2F;
        border: none;
        border-bottom: 1px solid #233249;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }
    QLabel#panelTitle {
        background: transparent;
        color: #F3F8FD;
        font-size: 15px;
        font-weight: 700;
    }
    QWidget#activeCamera {
        background: #02070D;
        color: #718096;
        border: none;
        font-size: 14px;
    }
    QFrame#cameraFooter {
        background: #0A1422;
        border: none;
        border-top: 1px solid #233249;
        border-bottom-left-radius: 8px;
        border-bottom-right-radius: 8px;
    }
    QLabel#cameraTelemetry {
        background: transparent;
        color: #8FA0B5;
        font-size: 11px;
    }
    QLabel#riskScore {
        background: transparent;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 62px;
        font-weight: 700;
    }
    QLabel#riskBand, QLabel#actionName {
        background: transparent;
        font-size: 19px;
        font-weight: 700;
    }
    QLabel#muted { background: transparent; color: #AFC0D4; font-size: 12px; }
    QFrame#riskHero, QFrame#actionHero {
        background: #111E2F;
        border: 1px solid #26364C;
        border-radius: 7px;
    }
    QLabel#scaleLabel {
        background: transparent;
        color: #718096;
        font-size: 9px;
    }
    QProgressBar#riskGauge {
        background: #1A2638;
        border: none;
        border-radius: 3px;
        min-height: 6px;
        max-height: 6px;
    }
    QProgressBar#riskGauge::chunk { background: #38BDF8; border-radius: 3px; }
    QFrame#actionIndicator { background: #38BDF8; border: none; border-radius: 2px; }
    QLabel#sectionTitle {
        background: transparent;
        color: #AFC0D4;
        font-size: 11px;
        font-weight: 650;
    }
    QFrame#decisionTelemetry {
        background: #0A1422;
        border: 1px solid #233249;
        border-radius: 7px;
    }
    QLabel#telemetryKey {
        background: transparent;
        color: #7F91A8;
        font-size: 11px;
        font-weight: 600;
    }
    QLabel#telemetryValue {
        background: transparent;
        color: #D8E4F1;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 11px;
        font-weight: 600;
    }
    QWidget#riskTrend {
        background: #0A1422;
        border: 1px solid #233249;
        border-radius: 7px;
    }
    QLabel#safetyNote {
        background: transparent;
        color: #718096;
        border-top: 1px solid #233249;
        padding-top: 8px;
        font-size: 10px;
    }
    QFrame#bottomMetric, QFrame#metricCell {
        background: #0D1828;
        border: none;
        border-right: 1px solid #233249;
        border-radius: 0;
    }
    QLabel#metricMono, QLabel#metricCellValue, QLabel#metricSmallValue, QLabel#metricValue {
        background: transparent;
        color: #F3F8FD;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 14px;
        font-weight: 650;
    }
    QPushButton, QToolButton {
        background: #111E2F;
        color: #C8D4E3;
        border: 1px solid #2B3B52;
        border-radius: 6px;
        min-height: 34px;
        padding: 3px 13px;
    }
    QPushButton:hover, QToolButton:hover { background: #17263A; border-color: #4A607C; color: #FFFFFF; }
    QPushButton:focus, QToolButton:focus { border: 2px solid #38BDF8; }
    QPushButton:checked, QToolButton:checked {
        background: #0B2940;
        color: #7DD3FC;
        border-color: #38BDF8;
    }
    QComboBox, QSpinBox, QLineEdit {
        background: #111E2F;
        color: #EAF2FB;
        border: 1px solid #2B3B52;
        border-radius: 6px;
        min-height: 32px;
        padding: 3px 8px;
    }
    QComboBox:focus, QSpinBox:focus, QLineEdit:focus { border: 2px solid #38BDF8; }
    QPlainTextEdit, QTextEdit {
        background: #07111F;
        color: #C8D4E3;
        border: none;
        font-family: Consolas, "Cascadia Mono", monospace;
        font-size: 11px;
        padding: 8px;
    }
    QTabWidget#diagnostics QTabBar::tab {
        background: #111E2F;
        color: #8FA0B5;
        border: 1px solid #233249;
        border-bottom: none;
        min-width: 76px;
        padding: 8px 14px;
    }
    QTabWidget#diagnostics QTabBar::tab:selected { background: #0D1828; color: #7DD3FC; border-color: #38BDF8; }
    QSplitter::handle { background: #07111F; width: 8px; }
    QLabel#statusOk { color: #34D399; font-weight: 650; background: transparent; }
    QLabel#statusWarn { color: #FBBF24; font-weight: 650; background: transparent; }
    QLabel#statusDanger { color: #F87171; font-weight: 650; background: transparent; }
    QStatusBar { background: #07111F; color: #8FA0B5; border-top: 1px solid #233249; }
    QScrollBar:vertical { background: transparent; width: 8px; }
    QScrollBar::handle:vertical { background: #34465F; min-height: 24px; border-radius: 4px; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    """
