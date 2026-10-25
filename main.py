"""北斋FGO助手（HFA）入口。

先开启 DPI 感知，保证多显示器/缩放场景下截图坐标和屏幕坐标一致。
"""
import ctypes
import sys


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> None:
    _enable_dpi_awareness()
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from app.main_window import MainWindow

    app = QApplication(sys.argv)
    font = QFont()
    font.setFamilies(["HarmonyOS Sans SC", "HarmonyOS Sans", "Microsoft YaHei UI"])
    font.setPointSize(10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
