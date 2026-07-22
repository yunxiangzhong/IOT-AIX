from __future__ import annotations


def app_stylesheet() -> str:
    """Apple-inspired Windows desktop surface with content-sized Chinese typography."""
    return r"""
    QWidget {
        background: #F5F5F7;
        color: #1D1D1F;
        font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif;
        font-size: 13px;
    }
    QMainWindow, QWidget#activeDashboard, QWidget#primaryPages, QWidget#workspaceSplitter,
    QWidget#rightControlSurface, QWidget#rightControlSurface > QWidget { background: #F5F5F7; }

    QFrame#globalNavigation, QFrame#visionPanel, QFrame#peripheralPanel, QFrame#realtimePanel,
    QFrame#decisionPanel, QFrame#upperComputerPanel, QFrame#pageHeader, QFrame#scenePanel,
    QFrame#deviceSheet, QTabWidget#diagnostics::pane {
        background: #FFFFFF;
        border: 1px solid #D8D8DC;
        border-radius: 14px;
    }
    QDialog#deviceWindow { background: transparent; }
    QDialog#diagnosticsWindow { background: #F5F5F7; }
    QFrame#globalNavigation { background: rgba(255, 255, 255, 238); }
    QLabel#appTitle { background: transparent; font-size: 21px; font-weight: 700; letter-spacing: -0.2px; }
    QLabel#pageTitle, QLabel#sheetTitle { background: transparent; font-size: 18px; font-weight: 700; }
    QLabel#panelTitle, QLabel#columnTitle { background: transparent; font-size: 15px; font-weight: 700; }
    QLabel#fieldLabel, QLabel#mappingLabel { background: transparent; color: #6E6E73; font-size: 11px; font-weight: 600; }
    QLabel#mappingValue { background: transparent; color: #1D1D1F; font-size: 12px; font-weight: 550; }
    QLabel#muted, QLabel#monoMuted, QLabel#cameraTelemetry, QLabel#metricTitle, QLabel#safetyNote {
        background: transparent; color: #6E6E73; font-size: 11px;
    }
    QLabel#monoMuted, QLabel#cameraTelemetry { font-family: "Cascadia Mono", Consolas, "Microsoft YaHei UI"; }
    QLabel#guardPrimary { background: transparent; color: #3A3A3C; font-size: 12px; font-weight: 600; }
    QLabel#hostStatusValue { background: transparent; color: #1D1D1F; font-size: 13px; font-weight: 650; }
    QLabel#trendDialogTitle { background: transparent; color: #1D1D1F; font-size: 17px; font-weight: 700; }
    QLabel#trendDialogStats { background: transparent; color: #6E6E73; font-size: 11px; }
    QDialog#trendDialog { background: #F5F5F7; }

    QFrame#panelHead, QFrame#cameraFooter {
        background: #FAFAFC; border: none; border-bottom: 1px solid #E5E5EA;
        border-top-left-radius: 13px; border-top-right-radius: 13px;
    }
    QFrame#cameraFooter {
        border-top: 1px solid #E5E5EA; border-bottom: none;
        border-top-left-radius: 0; border-top-right-radius: 0;
        border-bottom-left-radius: 13px; border-bottom-right-radius: 13px;
    }
    QWidget#activeCamera { background: #090A0C; color: #AEAEB2; border: none; }

    QFrame#mappingCell, QFrame#hostStatusCard, QFrame#scenarioInfoCard, QFrame#sheetStateCard {
        background: #FAFAFC; border: 1px solid #E5E5EA; border-radius: 10px;
    }
    QFrame#clickableStatusCard {
        background: #FAFAFC; border: 1px solid #E5E5EA; border-radius: 10px;
    }
    QFrame#clickableStatusCard:hover { background: #F2F7FF; border-color: #80B7FF; }
    QFrame#clickableStatusCard:focus { border: 2px solid #007AFF; }
    QFrame#clickableStatusCard[statusTone="ok"] { background: #ECF8EF; border-color: #B9DFC2; }
    QFrame#clickableStatusCard[statusTone="info"] { background: #EAF3FF; border-color: #80B7FF; }
    QFrame#clickableStatusCard[statusTone="attention"] { background: #FFF7E6; border-color: #E8C780; }
    QFrame#clickableStatusCard[statusTone="high"] { background: #FFF3ED; border-color: #F0B294; }
    QFrame#clickableStatusCard[statusTone="critical"] { background: #FFF0F1; border-color: #FFC1C5; }
    QFrame#clickableStatusCard[statusTone="fault"] { background: #F6F0FA; border-color: #D8BDE5; }
    QLabel#metricStatusIcon { background: transparent; }
    QLabel#metricTrendHint { background: transparent; color: #007AFF; font-size: 10px; font-weight: 600; }
    QFrame#guardBar {
        background: #F9F9FB; border: 1px solid #E5E5EA; border-radius: 10px;
    }
    QFrame#etaCard {
        background: #EEF6FF; border: 1px solid #B8D7FF; border-radius: 12px;
    }
    QLabel#etaValue {
        background: transparent; color: #007AFF; font-size: 34px; font-weight: 750;
        font-family: "Cascadia Mono", Consolas, "Microsoft YaHei UI";
    }
    QLabel#softBadge {
        background: #F2F2F7; color: #007AFF; border: 1px solid #C7D9F9;
        border-radius: 10px; padding: 4px 9px; font-size: 11px; font-weight: 650;
    }
    QLabel#softBadge[state="ok"] { background: #ECF8EF; color: #248A3D; border-color: #B9DFC2; }

    QFrame#scenarioStage {
        background: #FFFFFF; border: 1px solid #D8D8DC; border-radius: 10px;
    }
    QFrame#scenarioStage[stageState="active"] { background: #F3F8FF; border-color: #9FC7FF; }
    QFrame#scenarioStage[stageState="completed"] { background: #F1F8F2; border-color: #B9DFC2; }
    QFrame#scenarioStage[stageState="failed"] { background: #FFF2F2; border-color: #FFC1C5; }

    QPushButton, QToolButton {
        background: #FFFFFF; color: #1D1D1F; border: 1px solid #D2D2D7;
        border-radius: 9px; min-height: 32px; padding: 3px 12px;
    }
    QPushButton:hover, QToolButton:hover { background: #F2F2F7; border-color: #AEAEB2; }
    QPushButton:pressed, QToolButton:pressed { background: #E5E5EA; }
    QPushButton:focus, QToolButton:focus { border: 2px solid #007AFF; }
    QPushButton:checked, QToolButton:checked { background: #EAF3FF; color: #007AFF; border-color: #80B7FF; }
    QPushButton#primaryAction { background: #007AFF; color: #FFFFFF; border-color: #007AFF; font-weight: 650; }
    QPushButton#primaryAction:hover { background: #0066D6; }
    QPushButton#primaryAction:disabled { background: #C7C7CC; border-color: #C7C7CC; }
    QPushButton#dangerButton { background: #D70015; color: #FFFFFF; border-color: #D70015; font-weight: 700; }
    QPushButton#dangerButton:hover { background: #B80012; }
    QPushButton#dangerButton:disabled { background: #C7C7CC; border-color: #C7C7CC; }
    QPushButton#deviceStatusButton { min-width: 128px; font-weight: 650; }
    QPushButton#deviceStatusButton[connectionState="connected"] { color: #248A3D; background: #ECF8EF; border-color: #B9DFC2; }

    QComboBox, QSpinBox, QLineEdit {
        background: #FFFFFF; color: #1D1D1F; border: 1px solid #D2D2D7;
        border-radius: 8px; min-height: 32px; padding: 3px 9px;
    }
    QComboBox:focus, QSpinBox:focus, QLineEdit:focus { border: 2px solid #007AFF; }
    QMenu { background: #FFFFFF; border: 1px solid #D2D2D7; border-radius: 10px; padding: 6px; }
    QMenu::item { background: transparent; border-radius: 6px; padding: 7px 18px; }
    QMenu::item:selected { background: #EAF3FF; color: #007AFF; }
    QMenu::item:disabled { color: #86868B; }

    QPlainTextEdit, QTextEdit {
        background: #FAFAFC; color: #3A3A3C; border: none;
        font-family: "Cascadia Mono", Consolas, "Microsoft YaHei UI"; font-size: 11px; padding: 8px;
    }
    QTabWidget#diagnostics QTabBar::tab {
        background: #F2F2F7; color: #6E6E73; border: 1px solid #D2D2D7;
        border-bottom: none; min-width: 72px; padding: 8px 13px;
    }
    QTabWidget#diagnostics QTabBar::tab:selected { background: #FFFFFF; color: #007AFF; border-color: #80B7FF; }
    QStatusBar { background: #F5F5F7; color: #6E6E73; border-top: 1px solid #E5E5EA; }
    QScrollBar:vertical { background: transparent; width: 8px; }
    QScrollBar::handle:vertical { background: #C7C7CC; min-height: 24px; border-radius: 4px; }
    QLabel#statusOk { color: #248A3D; font-weight: 650; background: transparent; }
    QLabel#statusWarn { color: #A05A00; font-weight: 650; background: transparent; }
    QLabel#statusDanger { color: #D70015; font-weight: 650; background: transparent; }
    """
