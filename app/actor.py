"""鼠标点击操作模块。"""
from __future__ import annotations

import pyautogui

pyautogui.FAILSAFE = True   # 鼠标甩到屏幕左上角可紧急中止
pyautogui.PAUSE = 0.05


def click_at(x: int, y: int) -> None:
    """在屏幕绝对坐标处单击左键。"""
    pyautogui.click(int(x), int(y))


def rel_to_abs(
    rx: float, ry: float, client_rect: tuple[int, int, int, int]
) -> tuple[int, int]:
    """把相对窗口客户区的比例坐标 (0~1) 换算成屏幕绝对坐标。"""
    left, top, right, bottom = client_rect
    return (
        int(left + rx * (right - left)),
        int(top + ry * (bottom - top)),
    )
