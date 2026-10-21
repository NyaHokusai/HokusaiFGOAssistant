"""从愚人节 Q 版立绘（素材/图标.png）抠出完整角色并生成软件图标。

流程：
1. 浅色低饱和背景（白格线、淡紫格）且与画幅边缘连通 -> 判为背景剔除；
   角色有深色描边包裹，内部浅色不受影响。
2. 前景连通域中，保留最大组件（角色本体）以及与它膨胀接触的组件
   （飞溅墨滴等贴着角色的特效）；游离在外的栅栏柱残段不接触角色，被过滤。
输出 assets/icon.png（256x256 透明底）+ assets/icon.ico（多尺寸）。
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np
from PIL import Image

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(BASE_DIR, "assets")
SRC = os.path.join(os.path.dirname(BASE_DIR), "素材", "图标.png")
WORK = os.path.join(ASSETS, "_icon_work")
os.makedirs(WORK, exist_ok=True)
os.makedirs(ASSETS, exist_ok=True)


def imread_unicode(path: str) -> np.ndarray | None:
    data = np.fromfile(path, dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None


def remove_background(bgr: np.ndarray) -> np.ndarray:
    """返回 alpha mask（255=前景）。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    candidate = ((s < 105) & (v > 165)).astype(np.uint8)
    n, labels = cv2.connectedComponents(candidate, connectivity=4)
    border_labels = set(np.unique(np.concatenate([
        labels[0, :], labels[-1, :], labels[:, 0], labels[:, -1],
    ])).tolist())
    border_labels.discard(0)
    bg = np.isin(labels, list(border_labels))
    return (255 - bg * 255).astype(np.uint8)


def keep_main_component(alpha: np.ndarray) -> np.ndarray:
    """保留最大前景组件及其膨胀接触邻域内的组件。"""
    fg = (alpha > 128).astype(np.uint8)
    n, labels, stats, _ = cv2.connectedComponentsWithStats(fg, 8)
    if n <= 1:
        return alpha
    areas = stats[1:, cv2.CC_STAT_AREA]
    main_label = 1 + int(np.argmax(areas))
    # 主组件膨胀 7px，覆盖到的其他组件一并保留（墨滴等贴身特效）
    main_mask = (labels == main_label).astype(np.uint8)
    near = cv2.dilate(main_mask, np.ones((7, 7), np.uint8))
    main_area = int(areas.max())
    min_area = max(300, int(main_area * 0.01))  # 太小的碎片直接丢
    keep = np.zeros_like(alpha)
    for i in range(1, n):
        comp = labels == i
        if i == main_label or (near[comp].any() and stats[i, cv2.CC_STAT_AREA] >= min_area):
            keep[comp] = 255
    return keep


def main() -> int:
    bgr = imread_unicode(SRC)
    if bgr is None:
        print(f"[失败] 无法读取 {SRC}")
        return 1
    # 收紧画幅：左右栅栏主体直接裁掉，减小后续过滤压力
    h0, w0 = bgr.shape[:2]
    bgr = bgr[:, int(w0 * 0.08): int(w0 * 0.92)]

    alpha = remove_background(bgr)
    alpha = keep_main_component(alpha)
    # 轻微平滑边缘
    alpha = cv2.GaussianBlur(alpha, (3, 3), 0)

    rgba = np.dstack([bgr, alpha])
    ys, xs = np.where(alpha > 10)
    if len(xs) == 0:
        print("[失败] 抠图结果为空")
        return 1
    x1, x2, y1, y2 = xs.min(), xs.max(), ys.min(), ys.max()
    pad = 8
    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
    x2, y2 = min(rgba.shape[1] - 1, x2 + pad), min(rgba.shape[0] - 1, y2 + pad)
    rgba = rgba[y1 : y2 + 1, x1 : x2 + 1]

    # 补成正方形画布（角色居中）
    h, w = rgba.shape[:2]
    side = max(h, w) + 16
    canvas = np.zeros((side, side, 4), dtype=np.uint8)
    oy, ox = (side - h) // 2, (side - w) // 2
    canvas[oy : oy + h, ox : ox + w] = rgba

    # 中间产物供人工检查（透明区显示为白）
    check = canvas.copy()
    check[check[:, :, 3] == 0] = (255, 255, 255, 255)
    cv2.imwrite(os.path.join(WORK, "cutout_check.png"), check)

    icon_png = os.path.join(ASSETS, "icon.png")
    pil = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGRA2RGBA))
    pil.resize((256, 256), Image.LANCZOS).save(icon_png)
    print(f"[完成] {icon_png}")

    icon_ico = os.path.join(ASSETS, "icon.ico")
    pil.save(icon_ico, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"[完成] {icon_ico}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
