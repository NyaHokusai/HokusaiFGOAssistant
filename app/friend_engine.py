"""友情点召唤自动循环引擎。

流程（用户手动进入友情点召唤界面后点「开始」）：
  1. 识别「友情点召唤」画面 → 点击「召唤 x100」按钮（模板识别位置）
  2. 弹窗「决定」→ 点击识别到的按钮位置
  3. 每次点完「决定」（无论首抽还是继续召唤后）0.5 秒起每 0.5 秒点一次
     屏幕正中央跳过召唤动画，直到：
     - 识别到「继续进行100次召唤」→ 点击 → 弹窗「决定」→ 回到步骤 3
     - 识别到「友情点召唤」画面（友情点用完/结果翻完）→ 回到步骤 1
  4. 任意时刻识别到停止用素材图 → 自动停止

模板加载优先级：assets/templates/{key}.png > assets/templates/builtin/{key}.png
「决定」弹窗（friend_confirm）缺失时回退用补体力的通用「决定」模板。
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

FRIEND_LABELS = {
    "friend_summon": "友情点召唤",
    "friend_x100": "召唤 x100",
    "friend_confirm": "决定",
    "friend_continue": "继续进行100次召唤",
    "friend_stop": "停止素材",
}

# friend_confirm 缺省时回退用「决定」通用模板
FRIEND_FALLBACK = {"friend_confirm": ["confirm"]}

SKIP_DELAY = 0.5      # 点完决定后多久开始点屏幕中央
SKIP_INTERVAL = 0.5   # 跳动画连点的间隔
HOLD = 0.4            # 模板需持续出现的时间（防动画帧误判）
CLICK_GAP = 1.0       # 两次引擎点击的最小间隔（等画面切换）
POLL = 0.2

# 状态
S_WAIT_SUMMON = "wait_summon"    # 等友情点召唤画面 → 点 x100
S_WAIT_CONFIRM = "wait_confirm"  # 等「决定」弹窗
S_SKIP = "skip"                  # 连点屏幕中央跳动画，直到「继续进行100次召唤」


class FriendEngine(QThread):
    log_signal = Signal(str)
    state_signal = Signal(str)
    finished_ok = Signal(bool)

    def __init__(
        self,
        hwnd: int,
        template_dir: str,
        threshold: float = 0.8,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._hwnd = hwnd
        self._tpl_dir = template_dir
        self._threshold = threshold
        self._stop = False
        self._templates: dict = {}
        self._x100_point: tuple[float, float] | None = None
        self._state = S_WAIT_SUMMON
        self._skip_t0 = 0.0           # 开始连点屏幕中央的时间
        self._last_center = 0.0
        self._last_click = 0.0        # 任意引擎点击时间（限频）
        self._hold_since: dict[str, float] = {}

    def stop(self) -> None:
        self._stop = True

    # ---------- 资源加载 ----------
    def _load_one(self, key: str):
        user_path = os.path.join(self._tpl_dir, f"{key}.png")
        if os.path.exists(user_path):
            return load_template(user_path)
        builtin_path = os.path.join(self._tpl_dir, "builtin", f"{key}.png")
        if os.path.exists(builtin_path):
            return load_template(builtin_path)
        for fb in FRIEND_FALLBACK.get(key, []):
            tpl = self._load_one(fb)
            if tpl is not None:
                self.log_signal.emit(
                    f"[提示] 未录制「{FRIEND_LABELS[key]}」，回退使用「{fb}」模板")
                return tpl
        return None

    def _load_assets(self) -> None:
        for key in FRIEND_LABELS:
            tpl = self._load_one(key)
            if tpl is not None:
                self._templates[key] = tpl
        meta_path = os.path.join(self._tpl_dir, "meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                pt = meta.get("friend_x100") or {}
                self._x100_point = (float(pt["rx"]), float(pt["ry"]))
            except Exception:
                self._x100_point = None
        loaded = "、".join(FRIEND_LABELS[k] for k in FRIEND_LABELS if k in self._templates)
        self.log_signal.emit(f"[启动] 已加载模板: {loaded or '无'}")
        if "friend_x100" not in self._templates and self._x100_point is None:
            self.log_signal.emit("[警告] 「召唤 x100」模板与位置都没有，无法执行召唤步骤")
        if "friend_stop" not in self._templates:
            self.log_signal.emit("[提示] 未设置停止素材图，循环将一直进行直到手动结束")

    # ---------- 主循环 ----------
    def run(self) -> None:
        try:
            self._load_assets()
            self.state_signal.emit("监控中：等待友情点召唤画面…")
            while not self._stop:
                try:
                    self._poll()
                except RuntimeError as exc:
                    self.log_signal.emit(f"[错误] {exc}")
                    break
                except Exception as exc:
                    self.log_signal.emit(f"[错误] {exc!r}")
                    time.sleep(1.0)
                time.sleep(POLL)
        finally:
            self.finished_ok.emit(True)

    def _poll(self) -> None:
        if not win32gui.IsWindow(self._hwnd):
            raise RuntimeError("目标窗口已关闭，引擎停止")
        img = capture_window(self._hwnd)
        if img is None:
            return
        now = time.time()

        # 停止素材：任何状态出现都立即停
        stop_tpl = self._templates.get("friend_stop")
        if stop_tpl is not None:
            hit = find_template(img, stop_tpl, self._threshold)
            if hit is not None:
                self.log_signal.emit(
                    f"[完成] 识别到停止素材（得分 {hit[4]:.2f}），自动停止")
                self.state_signal.emit("已停止：识别到目标素材")
                self._stop = True
                return

        if self._state == S_WAIT_SUMMON:
            self._step_summon(img, now)
        elif self._state == S_WAIT_CONFIRM:
            self._step_confirm(img, now)
        elif self._state == S_SKIP:
            self._step_skip(img, now)

    # ---------- 状态处理 ----------
    def _step_summon(self, img, now: float) -> None:
        tpl = self._templates.get("friend_summon")
        if tpl is None:
            return  # start 时已校验，双保险
        hit = find_template(img, tpl, self._threshold)
        if hit is None:
            self._hold_since.pop("friend_summon", None)
            return
        since = self._hold_since.setdefault("friend_summon", now)
        if now - since < HOLD:
            return
        self._hold_since.pop("friend_summon", None)
        if now - self._last_click < CLICK_GAP:
            return
        wl, wt, wr, wb = get_client_rect_on_screen(self._hwnd)
        # 点击目标：优先「召唤 x100」模板识别位置；没有模板再用录入的点击位置
        x100_tpl = self._templates.get("friend_x100")
        x100_hit = (
            find_template(img, x100_tpl, self._threshold)
            if x100_tpl is not None else None
        )
        if x100_hit is not None:
            x, y, w, h, score = x100_hit
            cx, cy = wl + x + w // 2, wt + y + h // 2
            pos = f"「召唤 x100」识别位置（得分 {score:.2f}）"
        elif self._x100_point is not None:
            cx, cy = rel_to_abs(
                self._x100_point[0], self._x100_point[1], (wl, wt, wr, wb))
            pos = "录入的召唤位置"
        else:
            self.log_signal.emit("[警告] 找不到「召唤 x100」按钮且未录入位置，本轮跳过")
            return
        click_at(cx, cy)
        self._last_click = now
        self._state = S_WAIT_CONFIRM
        msg = f"识别到「友情点召唤」→ 已点{pos}，等待「决定」弹窗…"
        self.log_signal.emit(msg)
        self.state_signal.emit(msg)

    def _step_confirm(self, img, now: float) -> None:
        tpl = self._templates.get("friend_confirm")
        if tpl is None:
            return
        hit = find_template(img, tpl, self._threshold)
        if hit is None:
            self._hold_since.pop("friend_confirm", None)
            return
        since = self._hold_since.setdefault("friend_confirm", now)
        if now - since < HOLD:
            return
        self._hold_since.pop("friend_confirm", None)
        if now - self._last_click < CLICK_GAP:
            return
        x, y, w, h, score = hit
        wl, wt, wr, wb = get_client_rect_on_screen(self._hwnd)
        click_at(wl + x + w // 2, wt + y + h // 2)
        self._last_click = now
        # 无论首抽还是「继续召唤」后的决定，后面都有召唤动画，一律进跳动画阶段
        self._state = S_SKIP
        self._skip_t0 = now + SKIP_DELAY
        self._last_center = 0.0
        msg = f"「决定」已点（得分 {score:.2f}）→ 0.5 秒后连点屏幕中央跳过动画…"
        self.log_signal.emit(msg)
        self.state_signal.emit(msg)

    def _step_skip(self, img, now: float) -> None:
        # 1) 优先「继续进行100次召唤」：出现就点（等它时不再点中央）
        cont = self._templates.get("friend_continue")
        if cont is not None:
            hit = find_template(img, cont, self._threshold)
            if hit is not None:
                since = self._hold_since.setdefault("friend_continue", now)
                if now - since >= HOLD and now - self._last_click >= CLICK_GAP:
                    self._hold_since.pop("friend_continue", None)
                    x, y, w, h, score = hit
                    wl, wt, wr, wb = get_client_rect_on_screen(self._hwnd)
                    click_at(wl + x + w // 2, wt + y + h // 2)
                    self._last_click = now
                    self._state = S_WAIT_CONFIRM
                    msg = (f"识别到「继续进行100次召唤」（得分 {score:.2f}）"
                           "→ 已点击，等待「决定」弹窗…")
                    self.log_signal.emit(msg)
                    self.state_signal.emit(msg)
                return
            self._hold_since.pop("friend_continue", None)

        # 2) 回到「友情点召唤」画面（友情点用完/结果翻完）→ 退出跳动画，回主循环
        sm = self._templates.get("friend_summon")
        if sm is not None:
            hit = find_template(img, sm, self._threshold)
            if hit is not None:
                since = self._hold_since.setdefault("friend_summon", now)
                if now - since >= HOLD:
                    self._hold_since.pop("friend_summon", None)
                    self._state = S_WAIT_SUMMON
                    msg = "已回到友情点召唤画面 → 继续循环"
                    self.log_signal.emit(msg)
                    self.state_signal.emit(msg)
                return
            self._hold_since.pop("friend_summon", None)

        # 3) 都没出现：按节奏点屏幕正中央跳过召唤动画
        if now < self._skip_t0:
            return
        if now - self._last_center < SKIP_INTERVAL:
            return
        wl, wt, wr, wb = get_client_rect_on_screen(self._hwnd)
        click_at((wl + wr) // 2, (wt + wb) // 2)
        self._last_center = now
