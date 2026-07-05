from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6 import QtWidgets
    except ImportError:
        print("缺少 PySide6，请先在 host_app 目录安装 requirements.txt 中的依赖。")
        return 1

    from .app import MainWindow

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("AIX Pulse Helmet Host")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
