from __future__ import annotations


def app_stylesheet() -> str:
    """A restrained light system surface; state colour is applied only to status."""
    return """
    QWidget { background: #F5F5F7; color: #1D1D1F; font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif; font-size: 13px; }
    QMainWindow, QWidget#activeDashboard { background: #F5F5F7; }
    QFrame#instrumentHeader, QFrame#visionPanel, QFrame#decisionPanel, QFrame#metricBand,
    QFrame#panel, QFrame#peripheralPanel, QFrame#realtimePanel, QFrame#scenePanel,
    QFrame#chainStage, QTabWidget#diagnostics::pane {
        background: #FFFFFF; border: 1px solid #D2D2D7; border-radius: 12px;
    }
    QFrame#chainBand, QFrame#transparentFrame { background: transparent; border: none; }
    QLabel#instrumentTitle { background: transparent; color: #1D1D1F; font-size: 20px; font-weight: 700; }
    QLabel#instrumentSubtitle, QLabel#metricTitle, QLabel#muted, QLabel#monoMuted, QLabel#cameraTelemetry,
    QLabel#telemetryKey, QLabel#sectionTitle, QLabel#safetyNote { background: transparent; color: #6E6E73; font-size: 11px; }
    QLabel#headerTelemetry { background: transparent; border-left: 1px solid #D2D2D7; color: #3A3A3C; padding: 8px 14px; font-weight: 550; }
    QLabel#systemStatus, QLabel#softBadge { background: #F2F2F7; color: #007AFF; border: 1px solid #C7D9F9; border-radius: 10px; padding: 3px 9px; font-size: 11px; font-weight: 650; }
    QFrame#panelHead, QFrame#cameraFooter { background: #FAFAFC; border: none; border-bottom: 1px solid #E5E5EA; }
    QLabel#panelTitle { background: transparent; color: #1D1D1F; font-size: 15px; font-weight: 700; }
    QWidget#activeCamera { background: #161618; color: #AEAEB2; border: none; }
    QLabel#riskScore { background: transparent; font-family: "Cascadia Mono", Consolas, monospace; font-size: 56px; font-weight: 700; }
    QLabel#riskBand, QLabel#actionName { background: transparent; font-size: 18px; font-weight: 700; }
    QFrame#riskHero, QFrame#actionHero, QFrame#decisionTelemetry { background: #FAFAFC; border: 1px solid #E5E5EA; border-radius: 10px; }
    QLabel#telemetryValue, QLabel#metricMono, QLabel#metricCellValue, QLabel#metricSmallValue, QLabel#metricValue { background: transparent; color: #1D1D1F; font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px; font-weight: 600; }
    QProgressBar#riskGauge { background: #E5E5EA; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; }
    QProgressBar#riskGauge::chunk { background: #007AFF; border-radius: 3px; }
    QWidget#riskTrend { background: #FAFAFC; border: 1px solid #E5E5EA; border-radius: 10px; }
    QFrame#bottomMetric, QFrame#metricCell { background: #FFFFFF; border: none; border-right: 1px solid #E5E5EA; border-radius: 0; }
    QPushButton, QToolButton { background: #FFFFFF; color: #1D1D1F; border: 1px solid #D2D2D7; border-radius: 8px; min-height: 32px; padding: 3px 12px; }
    QPushButton:hover, QToolButton:hover { background: #F2F2F7; border-color: #AEAEB2; }
    QPushButton:pressed, QToolButton:pressed { background: #E5E5EA; padding-top: 5px; padding-bottom: 1px; }
    QPushButton:focus, QToolButton:focus { border: 2px solid #007AFF; }
    QPushButton:checked, QToolButton:checked { background: #EAF3FF; color: #007AFF; border-color: #007AFF; }
    QPushButton#primaryAction { background: #007AFF; color: white; border-color: #007AFF; font-weight: 650; }
    QPushButton#primaryAction:disabled { background: #C7C7CC; border-color: #C7C7CC; }
    QComboBox, QSpinBox, QLineEdit { background: #FFFFFF; color: #1D1D1F; border: 1px solid #D2D2D7; border-radius: 7px; min-height: 30px; padding: 3px 8px; }
    QPlainTextEdit, QTextEdit { background: #FAFAFC; color: #3A3A3C; border: none; font-family: "Cascadia Mono", Consolas, monospace; font-size: 11px; padding: 8px; }
    QTabWidget#diagnostics QTabBar::tab { background: #F2F2F7; color: #6E6E73; border: 1px solid #D2D2D7; border-bottom: none; min-width: 76px; padding: 8px 14px; }
    QTabWidget#diagnostics QTabBar::tab:selected { background: #FFFFFF; color: #007AFF; border-color: #007AFF; }
    QStatusBar { background: #F5F5F7; color: #6E6E73; border-top: 1px solid #D2D2D7; }
    QScrollBar:vertical { background: transparent; width: 8px; }
    QScrollBar::handle:vertical { background: #C7C7CC; min-height: 24px; border-radius: 4px; }
    QLabel#statusOk { color: #248A3D; font-weight: 650; background: transparent; }
    QLabel#statusWarn { color: #B25000; font-weight: 650; background: transparent; }
    QLabel#statusDanger { color: #D70015; font-weight: 650; background: transparent; }
    """
