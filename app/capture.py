"""窗口枚举与截图模块。

负责：
1. 枚举当前可见的顶级窗口（用于选择模拟器窗口）
2. 获取窗口客户区在屏幕上的坐标
3. 通过 mss 高速截取窗口客户区画面（BGR 格式，可直接给 OpenCV 用）
"""
from __future__ import annotations

import cv2
import numpy as np
import win32gui
import mss


def list_windows() -> list[tuple[int, str]]:
    """返回 [(hwnd, title), ...]，只含有标题的可见窗口。"""
    result: list[tuple[int, str]] = []

    def callback(hwnd: int, _: object) -> None:
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd)
        if title.strip():
            result.append((hwnd, title))

    win32gui.EnumWindows(callback, None)
    return result


def get_client_rect_on_screen(hwnd: int) -> tuple[int, int, int, int]:
    """返回窗口客户区在屏幕坐标系下的 (left, top, right, bottom)。

    注意：GetClientRect 返回 (0, 0, width, height)，left/top 恒为 0，
    宽高必须取 right-left / bottom-top（曾经错把 top 当下边界导致高度恒 0）。
    """
    left, top, right, bottom = win32gui.GetClientRect(hwnd)
    width, height = right - left, bottom - top
    pt = win32gui.ClientToScreen(hwnd, (left, top))
    return (pt[0], pt[1], pt[0] + width, pt[1] + height)


def capture_window(hwnd: int) -> np.ndarray | None:
    """截取窗口客户区，返回 BGR 图像。窗口无效时返回 None。"""
    if not win32gui.IsWindow(hwnd):
        return None
    left, top, right, bottom = get_client_rect_on_screen(hwnd)
    width, height = right - left, bottom - top
    if width <= 0 or height <= 0:
        return None
    with mss.mss() as sct:
        raw = sct.grab({"left": left, "top": top, "width": width, "height": height})
    img = np.asarray(raw)[:, :, :3]  # BGRA -> BGR
    return np.ascontiguousarray(img)


def crop_screen_rect(hwnd: int, rect: tuple[int, int, int, int]) -> np.ndarray | None:
    """从窗口当前画面中裁出屏幕坐标系下 rect=(x1,y1,x2,y2) 指定的区域。"""
    img = capture_window(hwnd)
    if img is None:
        return None
    wl, wt, wr, wb = get_client_rect_on_screen(hwnd)
    x1 = max(0, int(rect[0] - wl))
    y1 = max(0, int(rect[1] - wt))
    x2 = min(wr - wl, int(rect[2] - wl))
    y2 = min(wb - wt, int(rect[3] - wt))
    if x2 - x1 < 4 or y2 - y1 < 4:
        return None
    return img[y1:y2, x1:x2].copy()
