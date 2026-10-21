"""从截图生成内置模板。

用法：
1. 把文字截图（剪裁好的小图，或含该文字的整幅截图均可，整幅截图需为标准 16:9）放进
   项目根目录的 screenshots/ 文件夹，文件名对应：
     战斗结果.png / next.png        -> 战斗结果
     下一步.png / next.png          -> 下一步
     连续出击.png / attack.png      -> 连续出击
     助战选择.png / support.png     -> 助战选择
2. 运行:  python tools/make_builtin.py
3. 生成 assets/templates/builtin/{key}.png，重新打包 exe 或直接源码运行即可生效。

说明：
- 直接给剪裁好的小图最稳（就是聊天里那几张红框字图）。
- 自动做轻度裁边（去 2px 边框），并把 png 转成 BGR 三通道保存。
"""
from __future__ import annotations

import os
import sys

import cv2
import numpy as np

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIRS = [
    os.path.join(BASE_DIR, "screenshots"),
    os.path.dirname(BASE_DIR),  # 工作区根目录（如 素材/ 文件夹）
]
OUT_DIR = os.path.join(BASE_DIR, "assets", "templates", "builtin")

# 输出名 -> 候选输入文件名（相对 SRC_DIRS，也支持带子文件夹的路径）
MAPPING = {
    "battle_result": ["战斗结果.png", "battle_result.png", "素材/2,3-战斗结果.png"],
    "tap_start": ["请点击游戏界面.png", "tap_start.png", "素材/请点击游戏界面.png"],
    "next": ["下一步.png", "next.png", "素材/4-下一步.png"],
    "attack": ["连续出击.png", "attack.png", "素材/5-体力无体力判定-连续出击.png"],
    "support_title": ["助战选择.png", "support.png", "support_title.png", "素材/1-助战选择.png"],
    "apple": ["黄金果实.png", "apple.png", "素材/6-无体力-黄金果实.png"],
    "confirm": ["决定.png", "confirm.png", "素材/7-无体力决定.png"],
}


def _find(candidates: list[str]) -> str | None:
    for base in SRC_DIRS:
        for name in candidates:
            path = os.path.normpath(os.path.join(base, name))
            if os.path.exists(path):
                return path
    return None


def trim_border(img: np.ndarray, margin: int = 2) -> np.ndarray:
    h, w = img.shape[:2]
    m = min(margin, h // 4, w // 4)
    return img[m : h - m, m : w - m]


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    made = []
    for key, candidates in MAPPING.items():
        src = _find(candidates)
        if src is None:
            print(f"[跳过] {key}: 找不到 {candidates}")
            continue
        # cv2.imread 不支持中文路径，用 fromfile + imdecode 代替
        data = np.fromfile(src, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            print(f"[失败] 无法读取 {src}")
            continue
        if img.shape[1] > 1000:  # 疑似整幅截图，提示需要剪裁
            print(f"[警告] {src} 尺寸 {img.shape[1]}x{img.shape[0]}，看起来是整幅截图；请先剪出文字小图再重跑")
            continue
        out_path = os.path.join(OUT_DIR, f"{key}.png")
        cv2.imwrite(out_path, trim_border(img))
        print(f"[完成] {out_path} ({img.shape[1]}x{img.shape[0]})")
        made.append(key)
    if not made:
        print("没有生成任何模板。")
        return 1
    print(f"\n共生成 {len(made)} 个内置模板: {', '.join(made)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
