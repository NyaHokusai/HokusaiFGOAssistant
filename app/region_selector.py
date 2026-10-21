"""屏幕框选（v3：多显示器 + DPI 缩放全适配）。

- 每块显示器一个半透明遮罩窗口，所有屏幕（含副屏）都可框选。
- 选区一律用 Win32 GetCursorPos 的物理像素记录 —— 与 mss 截图、win32
  窗口坐标完全同一坐标系，125%/150% 缩放、混合 DPI 下都不会偏移。
- 画框时把物理坐标按各显示器的 (物理原点, 缩放) 映射到该屏遮罩的局部
  坐标，视觉与鼠标严格同步；跨屏拖拽时每块屏各自画出自己那一段。
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from PySide6.QtCore import QCoreApplication, QObject, Qt, QRect, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QWidget

Rect = tuple[int, int, int, int]

# ---- Win32: 显示器物理矩形 / 鼠标物理坐标 ----
_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM,
)


def _monitor_rects() -> list[tuple[int, int, int, int]]:
    """EnumDisplayMonitors：返回每块显示器的物理像素矩形 (l, t, r, b)。"""
    rects: list[tuple[int, int, int, int]] = []

    def cb(hmon, hdc, lprect, lparam) -> int:
        r = lprect.contents
        rects.append((int(r.left), int(r.top), int(r.right), int(r.bottom)))
        return 1

    ctypes.windll.user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(cb), 0)
    return rects


def cursor_physical() -> tuple[int, int]:
    """鼠标的 Windows 物理像素坐标（进程为 DPI aware 时即真实像素）。"""
    pt = wintypes.POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return (int(pt.x), int(pt.y))


class _Overlay(QWidget):
    """单块屏幕的半透明遮罩。"""

    def __init__(self, mgr: "RegionSelector", screen, phys_origin: tuple[int, int], dpr: float) -> None:
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self._mgr = mgr
        self._phys_origin = phys_origin
        self._dpr = dpr if dpr and dpr > 0 else 1.0
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)
        self.setGeometry(screen.geometry())

    # 物理 -> 该屏窗口局部（Qt 逻辑）
    def _to_local(self, p: tuple[int, int]) -> tuple[float, float]:
        return (
            (p[0] - self._phys_origin[0]) / self._dpr,
            (p[1] - self._phys_origin[1]) / self._dpr,
        )

    def paintEvent(self, _) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 110))
        sel = self._mgr.phys_rect()
        if sel is not None:
            x1, y1 = self._to_local((sel.x(), sel.y()))
            x2, y2 = self._to_local((sel.x() + sel.width(), sel.y() + sel.height()))
            local = QRect(int(x1), int(y1), int(round(x2 - x1)), int(round(y2 - y1)))
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(local, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(0, 200, 255), 2))
            painter.drawRect(local)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(local.x(), max(14, local.y() - 6), f"{sel.width()} x {sel.height}")
        painter.end()

    # ---- 鼠标/键盘：一律交给管理器用物理坐标处理 ----
    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._mgr.press()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._mgr.dragging:
            self._mgr.move()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._mgr.dragging:
            self._mgr.release()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key_Escape:
            self._mgr.cancel()


class RegionSelector(QObject):
    """多屏框选管理器。用 RegionSelector.select_region() 静态调用。"""

    selected = Signal(object)  # (x1, y1, x2, y2) 物理像素
    cancelled = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._overlays: list[_Overlay] = []
        self._phys_a: tuple[int, int] | None = None
        self._phys_b: tuple[int, int] | None = None
        self._running = False

    # ---- 生命周期 ----
    def start(self) -> None:
        monitors = _monitor_rects()
        for screen in QGuiApplication.screens():
            dpr = screen.devicePixelRatio() or 1.0
            g = screen.geometry()
            want_w, want_h = round(g.width() * dpr), round(g.height() * dpr)
            # 按尺寸匹配该 Qt 屏幕对应的物理显示器，再按原点就近消歧
            best = monitors[0] if monitors else (0, 0, 0, 0)
            best_score = float("inf")
            for r in monitors:
                if abs((r[2] - r[0]) - want_w) > 8 or abs((r[3] - r[1]) - want_h) > 8:
                    continue
                score = abs(r[0] - round(g.x() * dpr)) + abs(r[1] - round(g.y() * dpr))
                if score < best_score:
                    best, best_score = r, score
            self._overlays.append(_Overlay(self, screen, (best[0], best[1]), dpr))
        self._running = True
        cursor_logical = QCursor.pos()
        for ov in self._overlays:
            ov.show()
            ov.raise_()
        # 把焦点给鼠标所在屏的遮罩（Esc 生效），并激活窗口
        for ov in self._overlays:
            if ov.geometry().contains(cursor_logical):
                ov.activateWindow()
                ov.setFocus()
                break

    def close_all(self) -> None:
        self._running = False
        for ov in self._overlays:
            ov.close()

    def is_running(self) -> bool:
        return self._running

    # ---- 选区状态 ----
    @property
    def dragging(self) -> bool:
        return self._phys_a is not None

    def phys_rect(self) -> QRect | None:
        if self._phys_a is None or self._phys_b is None:
            return None
        x1, x2 = sorted((self._phys_a[0], self._phys_b[0]))
        y1, y2 = sorted((self._phys_a[1], self._phys_b[1]))
        return QRect(x1, y1, x2 - x1, y2 - y1)

    def _refresh(self) -> None:
        for ov in self._overlays:
            ov.update()

    # ---- 鼠标事件入口 ----
    def press(self) -> None:
        self._phys_a = self._phys_b = cursor_physical()
        self._refresh()

    def move(self) -> None:
        self._phys_b = cursor_physical()
        self._refresh()

    def release(self) -> None:
        self._phys_b = cursor_physical()
        rect = self.phys_rect()
        ok = rect is not None and rect.width() >= 4 and rect.height() >= 4
        self.close_all()
        if ok:
            self.selected.emit(
                (rect.x(), rect.y(), rect.x() + rect.width(), rect.y() + rect.height())
            )
        else:
            self.cancelled.emit()

    def cancel(self) -> None:
        self.close_all()
        self.cancelled.emit()

    # ---- 静态便捷调用 ----
    @staticmethod
    def select_region() -> Rect | None:
        """阻塞式框选，返回物理像素 (x1,y1,x2,y2)；Esc/无效返回 None。"""
        sel = RegionSelector()
        result: dict = {}
        sel.selected.connect(lambda r: result.update(r=r))
        sel.start()
        while sel.is_running():
            QCoreApplication.processEvents()
            time.sleep(0.02)
        sel.deleteLater()
        return result.get("r")
