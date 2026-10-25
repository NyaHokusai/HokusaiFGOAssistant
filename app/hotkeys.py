"""全局快捷键（RegisterHotKey + Qt 原生事件过滤器）。

即使 HFA 窗口不在前台（用户在模拟器里操作），按下快捷键也能触发。
每个功能一个 id，按一次在「开始/结束」之间切换（由 MainWindow 决定动作）。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, Qt
from PySide6.QtGui import QKeySequence

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008

_MOD_MAP = {
    Qt.KeyboardModifier.ControlModifier: MOD_CONTROL,
    Qt.KeyboardModifier.AltModifier: MOD_ALT,
    Qt.KeyboardModifier.ShiftModifier: MOD_SHIFT,
    Qt.KeyboardModifier.MetaModifier: MOD_WIN,
}

# Qt.Key -> Windows VK（覆盖常用：F1~F24、字母、数字、方向/编辑键、符号）
_SPECIAL_VK = {
    Qt.Key_Space: 0x20, Qt.Key_Tab: 0x09, Qt.Key_Backtab: 0x0A,
    Qt.Key_Backspace: 0x08, Qt.Key_Return: 0x0D, Qt.Key_Escape: 0x1B,
    Qt.Key_Insert: 0x2D, Qt.Key_Delete: 0x2E, Qt.Key_Home: 0x24,
    Qt.Key_End: 0x23, Qt.Key_PageUp: 0x21, Qt.Key_PageDown: 0x22,
    Qt.Key_Left: 0x25, Qt.Key_Up: 0x26, Qt.Key_Right: 0x27, Qt.Key_Down: 0x28,
    Qt.Key_Pause: 0x13, Qt.Key_ScrollLock: 0x91, Qt.Key_Print: 0x2A,
    Qt.Key_Minus: 0xBD, Qt.Key_Equal: 0xBB, Qt.Key_BracketLeft: 0xDB,
    Qt.Key_BracketRight: 0xDD, Qt.Key_Semicolon: 0xBA,
    Qt.Key_Apostrophe: 0xC0, Qt.Key_Comma: 0xBC, Qt.Key_Period: 0xBE,
    Qt.Key_Slash: 0xBF, Qt.Key_Backslash: 0xDC,
}


def _qtkey_to_vk(key: Qt.Key) -> int | None:
    if Qt.Key_F1 <= key <= Qt.Key_F24:
        return 0x70 + (key - Qt.Key_F1)
    if (0x30 <= key <= 0x39) or (0x41 <= key <= 0x5A):  # 0-9 / A-Z
        return int(key)
    return _SPECIAL_VK.get(key)


def seq_to_vk_mod(text: str) -> tuple[int, int] | None:
    """把 QKeySequence 文本转成 (vk, modifiers)；不是单个按键返回 None。"""
    if not text:
        return None
    seq = QKeySequence(text)
    if seq.count() != 1:
        return None
    combo = seq[0]
    key = combo.key()
    vk = _qtkey_to_vk(key)
    if vk is None:
        return None
    mod = 0
    mods = combo.keyboardModifiers()
    for qmod, wmod in _MOD_MAP.items():
        if mods & qmod:
            mod |= wmod
    return vk, mod


class HotkeyManager(QAbstractNativeEventFilter):
    """注册/注销全局热键并分发 WM_HOTKEY。callback(hid: int)。"""

    def __init__(self, callback) -> None:
        super().__init__()
        self._cb = callback
        self._regs: dict[int, tuple[int, int]] = {}

    def register(self, hid: int, text: str) -> bool:
        self.unregister(hid)
        vm = seq_to_vk_mod(text)
        if vm is None:
            return False
        vk, mod = vm
        if not ctypes.windll.user32.RegisterHotKey(None, hid, mod, vk):
            return False
        self._regs[hid] = (vk, mod)
        return True

    def unregister(self, hid: int) -> None:
        if hid in self._regs:
            ctypes.windll.user32.UnregisterHotKey(None, hid)
            del self._regs[hid]

    def unregister_all(self) -> None:
        for hid in list(self._regs):
            self.unregister(hid)

    def nativeEventFilter(self, eventType, message):  # noqa: N802
        if eventType == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and msg.wParam in self._regs:
                    self._cb(int(msg.wParam))
            except Exception:
                pass
        return False, 0
