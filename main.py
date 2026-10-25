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
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    # 显式声明缩放策略：125%/150% 等分数缩放按原样传递，禁止取整，
    # 否则 Qt 按 1x 渲染再由 DWM 拉伸，整个界面发糊。
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    from app.main_window import MainWindow

    app = QApplication(sys.argv)
    font = QFont()
    # 优先 HarmonyOS Sans 自带的 Light 细体，没装则回退常规体
    font.setFamilies([
        "HarmonyOS Sans SC Light", "HarmonyOS Sans Light",
        "HarmonyOS Sans SC", "HarmonyOS Sans", "Microsoft YaHei UI",
    ])
    font.setPointSize(10)
    app.setFont(font)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
