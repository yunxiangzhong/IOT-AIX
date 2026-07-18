from __future__ import annotations

import os
from pathlib import Path

from PySide6 import QtGui, QtWidgets


_LOADED_FAMILY = ""


def ensure_cjk_font() -> str:
    """Install one system-like CJK application font without component-level overrides."""
    global _LOADED_FAMILY
    if _LOADED_FAMILY:
        return _LOADED_FAMILY
    fonts_root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = (fonts_root / "msyh.ttc", fonts_root / "NotoSansSC-VF.ttf", fonts_root / "simhei.ttf")
    for path in candidates:
        if not path.is_file():
            continue
        font_id = QtGui.QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
        if families:
            preferred = next((family for family in families if "YaHei UI" in family), families[0])
            _LOADED_FAMILY = preferred
            app = QtWidgets.QApplication.instance()
            if app is not None:
                font = QtGui.QFont(_LOADED_FAMILY)
                font.setPointSizeF(10.0)
                font.setStyleStrategy(QtGui.QFont.StyleStrategy.PreferAntialias)
                app.setFont(font)
            return _LOADED_FAMILY
    app = QtWidgets.QApplication.instance()
    if app is not None:
        font = QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.GeneralFont)
        font.setPointSizeF(10.0)
        app.setFont(font)
        _LOADED_FAMILY = font.family()
        return _LOADED_FAMILY
    return "Microsoft YaHei UI"
