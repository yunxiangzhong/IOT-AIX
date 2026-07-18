from __future__ import annotations

import os
from pathlib import Path

from PySide6 import QtGui, QtWidgets


_LOADED_FAMILY = ""


def ensure_cjk_font() -> str:
    """Register a known Windows CJK font so Qt offscreen/sandbox rendering stays readable."""
    global _LOADED_FAMILY
    if _LOADED_FAMILY:
        return _LOADED_FAMILY
    fonts_root = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    candidates = (
        fonts_root / "NotoSansSC-VF.ttf",
        fonts_root / "Noto Sans SC (TrueType).otf",
        fonts_root / "msyh.ttc",
        fonts_root / "simhei.ttf",
    )
    for path in candidates:
        if not path.is_file():
            continue
        font_id = QtGui.QFontDatabase.addApplicationFont(str(path))
        if font_id < 0:
            continue
        families = QtGui.QFontDatabase.applicationFontFamilies(font_id)
        if families:
            _LOADED_FAMILY = families[0]
            app = QtWidgets.QApplication.instance()
            if app is not None:
                app.setFont(QtGui.QFont(_LOADED_FAMILY, 9))
            return _LOADED_FAMILY
    return QtWidgets.QApplication.font().family()
