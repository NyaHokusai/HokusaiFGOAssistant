"""基于 OpenCV 模板匹配的界面识别模块。"""
from __future__ import annotations

import cv2
import numpy as np

Match = tuple[int, int, int, int, float]  # (x, y, w, h, score)


def load_template(path: str) -> np.ndarray | None:
    """读取模板图；用 fromfile+imdecode 兼容中文/特殊字符路径。"""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except OSError:
        return None


def find_template(
    screen_bgr: np.ndarray,
    template: str | np.ndarray,
    threshold: float = 0.8,
) -> Match | None:
    """在整幅窗口画面中查找模板（路径或已加载图像），得分 >= threshold 才算命中。"""
    tpl = template if isinstance(template, np.ndarray) else load_template(template)
    if tpl is None or screen_bgr is None:
        return None
    th, tw = tpl.shape[:2]
    if screen_bgr.shape[0] < th or screen_bgr.shape[1] < tw:
        return None
    res = cv2.matchTemplate(screen_bgr, tpl, cv2.TM_CCOEFF_NORMED)
    _, maxv, _, maxloc = cv2.minMaxLoc(res)
    if maxv >= threshold:
        x, y = maxloc
        return (x, y, tw, th, float(maxv))
    return None
