"""FGO 对局结束自动处理引擎（v2：内置模板 + 持续 n 秒防抖）。

流程（战斗本体玩家手动打，引擎只接管结算）：
  1. 「决定」（行动力确认弹窗，可选模板）→ 点击
  2. 「黄金果实」（行动力回复弹窗，可选模板）→ 点击金苹果
  3. 「战斗结果」标题 → 持续 n 秒 → 点击屏幕正中央（结算第 1、2 页都靠它）
  4. 「下一步」→ 持续 n 秒 → 点击识别到的位置
  5. 「连续出击」→ 持续 n 秒 → 点击识别到的位置
  6. 「助战选择」标题 → 持续 n 秒 → 点击玩家录入的助战位置

模板加载优先级：assets/templates/{key}.png（用户框选的覆盖版）
             > assets/templates/builtin/{key}.png（内置抠图版）
"""
from __future__ import annotations

import json
import os
import time

import win32gui
from PySide6.QtCore import QThread, Signal

from .actor import click_at, rel_to_abs
from .capture import capture_window, get_client_rect_on_screen
from .recognizer import find_template, load_template

TEMPLATE_LABELS = {
    "battle_result": "战斗结果",
    "tap_start": "请点击游戏界面",
    "next": "下一步",
    "attack": "连续出击",
    "apple": "黄金果实",
    "confirm": "决定",
    "support_title": "助战选择",
}

# 点击方式：center=屏幕正中央；match=模板命中位置；point=录入的助战位置
CLICK_ACTION = {
    "battle_result": "center",
    "tap_start": "center",
    "next": "match",
    "attack": "match",
    "apple": "match",
    "confirm": "match",
    "support": "point",
}

# 检测优先级：补体力弹窗最先（此时连续出击已消失），再走结算流程，最后助战
PRIORITY = ["confirm", "apple", "battle_result", "tap_start", "next", "attack", "support"]

SAME_KEY_COOLDOWN = 2.0  # 同一模板两次点击的最小间隔（等画面切换）
GLOBAL_GAP = 0.5         # 任意两次点击的最小间隔
POLL_INTERVAL = 0.25


class FgoEngine(QThread):
    log_signal = Signal(str)
    state_signal = Signal(str)
    finished_ok = Signal(bool)

    def __init__(
        self,
        hwnd: int,
        template_dir: str,
        threshold: float = 0.8,
        hold_seconds: float = 1.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._hwnd = hwnd
        self._tpl_dir = template_dir
        self._threshold = threshold
        self._hold_seconds = max(0.0, hold_seconds)
        self._stop = False
        self._templates: dict = {}
        self._support_points: dict[str, tuple[float, float]] = {}  # "1"/"2"/"3" -> (rx, ry)
        self.use_row = 1  # 当前使用的助行行号，UI 可随时切换（set_use_row）
        self._row_fallback_logged = False
        self._last_click: dict[str, float] = {}
        self._last_any = 0.0
        self._hold_since: dict[str, float] = {}  # key -> 首次连续命中的时间

    def stop(self) -> None:
        self._stop = True

    def set_use_row(self, row: int) -> None:
        """UI 运行中切换使用的助战行（1~3）。"""
        self.use_row = max(1, min(3, row))
        self.log_signal.emit(f"[切换] 助战改为第 {self.use_row} 行")

    # ---------- 资源加载 ----------
    def _load_one(self, key: str):
        user_path = os.path.join(self._tpl_dir, f"{key}.png")
        if os.path.exists(user_path):
            return load_template(user_path)
        builtin_path = os.path.join(self._tpl_dir, "builtin", f"{key}.png")
        if os.path.exists(builtin_path):
            return load_template(builtin_path)
        return None

    def _load_assets(self) -> None:
        for key in TEMPLATE_LABELS:
            tpl = self._load_one(key)
            if tpl is not None:
                self._templates[key] = tpl
        meta_path = os.path.join(self._tpl_dir, "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                rows = meta.get("support_rows") or {}
                # 兼容旧版单行字段
                if "support_row" in meta and "1" not in rows:
                    rows["1"] = meta["support_row"]
                for k, pt in rows.items():
                    try:
                        self._support_points[str(k)] = (float(pt["rx"]), float(pt["ry"]))
                    except Exception:
                        continue
            except Exception:
                pass
        loaded = "、".join(TEMPLATE_LABELS[k] for k in TEMPLATE_LABELS if k in self._templates)
        self.log_signal.emit(f"[启动] 已加载模板: {loaded or '无'}")
        if self._support_points:
            rows_txt = "、".join(sorted(self._support_points))
            self.log_signal.emit(f"[启动] 助战位置已就绪: 第 {rows_txt} 行（当前使用第 {self.use_row} 行）")
        elif "support_title" in self._templates:
            self.log_signal.emit("[警告] 未录入任何助战点击位置，助战步骤将跳过")

    # ---------- 主循环 ----------
    def run(self) -> None:
        try:
            self._load_assets()
            self.state_signal.emit("监控中：等待战斗结束画面…")
            while not self._stop:
                try:
                    self._poll()
                except RuntimeError as exc:
                    self.log_signal.emit(f"[错误] {exc}")
                    break
                except Exception as exc:
                    self.log_signal.emit(f"[错误] {exc!r}")
                    time.sleep(1.0)
                time.sleep(POLL_INTERVAL)
        finally:
            self.finished_ok.emit(True)

    def _poll(self) -> None:
        if not win32gui.IsWindow(self._hwnd):
            raise RuntimeError("目标窗口已关闭，引擎停止")
        img = capture_window(self._hwnd)
        if img is None:
            return
        now = time.time()
        if now - self._last_any < GLOBAL_GAP:
            return

        for key in PRIORITY:
            if self._stop:
                return
            if self._check_key(key, img, now):
                return

    def _check_key(self, key: str, img, now: float) -> bool:
        """检测单个状态；命中且持续满 n 秒则点击。返回 True 表示本轮已处理该状态。"""
        if key == "support":
            tpl = self._templates.get("support_title")
            if tpl is None:
                return False
            hit = find_template(img, tpl, self._threshold)
            if hit is None:
                self._hold_since.pop("support", None)
                return False
            if not self._support_points:
                return True  # 已识别但没录任何点击位置，挡住后面状态避免误点
            return self._fire(key, hit, now)

        tpl = self._templates.get(key)
        if tpl is None:
            return False
        hit = find_template(img, tpl, self._threshold)
        if hit is None:
            self._hold_since.pop(key, None)
            return False
        return self._fire(key, hit, now)

    def _fire(self, key: str, hit: tuple, now: float) -> bool:
        x, y, w, h, score = hit
        since = self._hold_since.get(key)
        if since is None:
            self._hold_since[key] = now
            self.state_signal.emit(
                f"识别到「{TEMPLATE_LABELS.get(key, key)}」（{score:.2f}），持续 {self._hold_seconds:.1f} 秒后点击…"
            )
            return True
        if now - since < self._hold_seconds:
            return True  # 还没持续够 n 秒
        if now - self._last_click.get(key, 0.0) < SAME_KEY_COOLDOWN:
            return True  # 刚点过、画面还没切走
        self._hold_since.pop(key, None)

        wl, wt, wr, wb = get_client_rect_on_screen(self._hwnd)
        action = CLICK_ACTION.get(key, "match")
        if action == "center":
            cx, cy = (wl + wr) // 2, (wt + wb) // 2
            pos_desc = "屏幕正中央"
        elif action == "point" and self._support_points:
            # 优先当前选中行；未录入则回退到任意已录入的行
            row_key = str(self.use_row)
            pt = self._support_points.get(row_key)
            if pt is None:
                row_key = sorted(self._support_points)[0]
                pt = self._support_points[row_key]
                if not self._row_fallback_logged:
                    self._row_fallback_logged = True
                    self.log_signal.emit(
                        f"[警告] 第 {self.use_row} 行未录入，暂用第 {row_key} 行位置"
                    )
            cx, cy = rel_to_abs(pt[0], pt[1], (wl, wt, wr, wb))
            pos_desc = f"第 {row_key} 行助战位置"
        else:
            cx, cy = wl + x + w // 2, wt + y + h // 2
            pos_desc = f"识别位置 ({x + w // 2}, {y + h // 2})"
        click_at(cx, cy)
        self._mark(key, now)
        msg = f"「{TEMPLATE_LABELS.get(key, key)}」已持续 {self._hold_seconds:.1f}s（得分 {score:.2f}）→ 点击{pos_desc}"
        self.log_signal.emit(msg)
        self.state_signal.emit(msg)
        return True

    def _mark(self, key: str, now: float) -> None:
        self._last_click[key] = now
        self._last_any = now
