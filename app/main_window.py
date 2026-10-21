"""北斋FGO助手 - 主界面（现代深色主题：侧边栏 + 毛玻璃卡片）。

布局：左侧导航栏（运行 / 模板 / 设置 / 日志），右侧堆叠页面。
开始后引擎持续监控模拟器画面，自动完成：
战斗结果 → 请点击游戏界面 → 下一步 → 连续出击 →（没体力吃金苹果）→ 选中的助战行。
战斗本体由玩家手动打，打完引擎自动接管。
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import time

import cv2
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .capture import crop_screen_rect, get_client_rect_on_screen, list_windows
from .fgo_engine import FgoEngine
from .region_selector import RegionSelector

if getattr(sys, "frozen", False):  # PyInstaller 打包后，资源放 exe 旁边，方便用户修改
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "assets", "templates")
META_PATH = os.path.join(TEMPLATE_DIR, "meta.json")

# (key, 界面显示说明)；助战行位置单独处理
TEMPLATE_SLOTS = [
    ("battle_result", "「战斗结果」标题", "结算页识别，点屏幕正中央"),
    ("tap_start", "「请点击游戏界面」", "点屏幕正中央"),
    ("next", "「下一步」按钮", "点击识别位置"),
    ("attack", "「连续出击」按钮", "点击识别位置"),
    ("apple", "黄金果实行", "没体力时自动补体力（可选）"),
    ("confirm", "「决定」按钮", "补体力确认弹窗（可选）"),
    ("support_title", "「助战选择」标题", "识别助战界面"),
]

# ============ 主题（深空科技：8pt 网格 + 12px 圆角 + 克制阴影） ============
_T = {
    "bg":          (13, 13, 26),
    "sidebar":     (22, 22, 40),
    "card":        (255, 255, 255, 10),   # rgba alpha 0~255
    "card_border": (255, 255, 255, 18),
    "primary":     "#6C63FF",
    "primary_h":   "#7D75FF",
    "text":        "#E8E8F2",
    "muted":       "#9A9AB0",
    "success":     "#3ECFCF",
    "danger":      "#FF6584",
    "builtin":     "#7B9DFF",
}

_BACKDROP_ALPHA = 0.72  # 毛玻璃激活时根背景透明度（透过 Acrylic 看到 blur）


def _rgba(rgb, alpha: float) -> str:
    r, g, b = rgb[0], rgb[1], rgb[2]
    return f"rgba({r}, {g}, {b}, {alpha})"


def build_stylesheet(solid: bool) -> str:
    """生成全局 QSS。solid=True 时背景不透明（系统不支持毛玻璃的回退）。"""
    a = 1.0 if solid else _BACKDROP_ALPHA
    card_a = 0.08 if solid else 0.05
    t = _T
    return f"""
    QWidget {{ color: {t['text']}; font-size: 13px; }}
    #root {{ background: {_rgba(t['bg'], a)}; }}
    #sidebar {{
        background: {_rgba(t['sidebar'], a if not solid else 1.0)};
        border-right: 1px solid {_rgba(t['card_border'], 0.6)};
    }}
    QLabel#appTitle {{ font-size: 16px; font-weight: 700; }}
    QLabel#appSub {{ font-size: 10px; color: {t['muted']}; letter-spacing: 3px; }}
    QLabel#sectionTitle {{ font-size: 15px; font-weight: 700; }}
    QLabel#muted {{ color: {t['muted']}; }}

    QPushButton#nav {{
        text-align: left; padding: 0 14px; min-height: 38px;
        border: none; border-radius: 10px; background: transparent;
        color: {t['muted']}; font-size: 13px; font-weight: 600;
    }}
    QPushButton#nav:hover {{ background: rgba(255, 255, 255, 0.07); color: {t['text']}; }}
    QPushButton#nav:checked {{ background: rgba(108, 99, 255, 0.22); color: {t['text']}; }}

    QFrame#card {{
        background: rgba(255, 255, 255, {card_a});
        border: 1px solid {_rgba(t['card_border'], 0.6)};
        border-radius: 12px;
    }}
    QFrame#card[flat="true"] {{ background: transparent; border: none; }}

    QPushButton {{
        background: rgba(255, 255, 255, {card_a + 0.03}); color: {t['text']};
        border: 1px solid {_rgba(t['card_border'], 0.6)};
        border-radius: 10px; padding: 0 16px; min-height: 34px; font-weight: 600;
    }}
    QPushButton:hover {{ background: rgba(255, 255, 255, 0.14); }}
    QPushButton:pressed {{ background: rgba(255, 255, 255, 0.08); }}
    QPushButton:disabled {{ color: {t['muted']}; background: rgba(255, 255, 255, 0.03); }}
    QPushButton#primary {{ background: {t['primary']}; border: none; color: white; }}
    QPushButton#primary:hover {{ background: {t['primary_h']}; }}
    QPushButton#primary:disabled {{ background: {_rgba((108, 99, 255), 0.35)}; color: rgba(255,255,255,0.6); }}
    QPushButton#danger {{ background: transparent; color: {t['danger']}; border: 1px solid rgba(255,101,132,0.5); }}
    QPushButton#danger:hover {{ background: rgba(255,101,132,0.15); }}
    QPushButton#danger:disabled {{ color: {t['muted']}; border-color: {_rgba(t['card_border'], 0.5)}; }}

    QComboBox, QDoubleSpinBox {{
        background: rgba(255, 255, 255, {card_a + 0.03}); border: 1px solid {_rgba(t['card_border'], 0.6)};
        border-radius: 10px; min-height: 34px; padding: 0 10px; color: {t['text']};
    }}
    QComboBox:hover, QDoubleSpinBox:hover {{ border-color: {t['primary']}; }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox QAbstractItemView {{
        background: #16162A; border: 1px solid {_rgba(t['card_border'], 0.8)};
        border-radius: 10px; selection-background-color: rgba(108,99,255,0.35);
        outline: none;
    }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 18px; }}

    QRadioButton {{ spacing: 6px; }}
    QRadioButton::indicator {{
        width: 16px; height: 16px; border-radius: 8px;
        border: 2px solid {t['muted']}; background: transparent;
    }}
    QRadioButton::indicator:checked {{ border: 5px solid {t['primary']}; background: white; }}

    QPlainTextEdit#log {{
        background: {_rgba(t['card'], 0.9)}; border: 1px solid {_rgba(t['card_border'], 0.6)};
        border-radius: 12px; padding: 10px;
        font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; color: #C8C8DE;
    }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {_rgba(t['card_border'], 0.9)}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    """


def _enable_backdrop(hwnd: int) -> bool:
    """开启系统级毛玻璃。返回是否成功（Win11 Acrylic 优先，Win10 走 Accent 兜底）。"""
    # 深色模式（标题栏）
    dark = ctypes.c_int(1)
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
    except Exception:
        pass
    # Win11 22H2+ Acrylic
    try:
        val = ctypes.c_int(3)  # DWMSBT_TRANSIENTWINDOW = Acrylic
        ret = ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 38, ctypes.byref(val), 4)
        if ret == 0:
            return True
    except Exception:
        pass
    # Win10 Acrylic (SetWindowCompositionAttribute)
    try:
        class ACCENTPOLICY(ctypes.Structure):
            _fields_ = [
                ("AccentState", ctypes.c_int),
                ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint),
                ("AnimationId", ctypes.c_int),
            ]

        class WINCOMPATTRDATA(ctypes.Structure):
            _fields_ = [
                ("Attribute", ctypes.c_int),
                ("Data", ctypes.c_void_p),
                ("SizeOfData", ctypes.c_size_t),
            ]

        accent = ACCENTPOLICY(4, 2, 0xCC000000, 0)  # 4=AcrylicBlurBehind，黑色 tint
        data = WINCOMPATTRDATA(
            19, ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p), ctypes.sizeof(accent)
        )
        if ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, ctypes.byref(data)):
            return True
    except Exception:
        pass
    return False


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("北斋FGO助手 HokusaiFGOAssistant (HFA)")
        icon_png = os.path.normpath(os.path.join(TEMPLATE_DIR, "..", "icon.png"))
        if os.path.exists(icon_png):
            self.setWindowIcon(QIcon(icon_png))
        self.resize(920, 660)

        os.makedirs(TEMPLATE_DIR, exist_ok=True)
        self._engine: FgoEngine | None = None
        self._cfg_path = os.path.join(BASE_DIR, "config.json")
        self._cfg = self._load_config()
        self._backdrop_ok = False
        self._solid_applied = False

        # 毛玻璃需要窗口背景可透出系统模糊层
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setStyleSheet(build_stylesheet(solid=False))

        self._build_ui()
        self._apply_config()
        self.refresh_windows()
        self._restore_window_selection()
        self._refresh_template_status()

    # ================= 毛玻璃 =================
    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._backdrop_ok and not self._solid_applied:
            QTimer.singleShot(0, self._try_backdrop)

    def _try_backdrop(self) -> None:
        try:
            hwnd = int(self.winId())
        except Exception:
            return
        self._backdrop_ok = _enable_backdrop(hwnd)
        if not self._backdrop_ok:
            self._solid_applied = True
            self.setStyleSheet(build_stylesheet(solid=True))

    # ================= 配置持久化 =================
    def _load_config(self) -> dict:
        if os.path.exists(self._cfg_path):
            try:
                with open(self._cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self) -> None:
        cfg = {
            "window_title": self.win_combo.currentText(),
            "threshold": self.threshold_spin.value(),
            "hold_seconds": self.hold_spin.value(),
            "use_row": self._current_use_row(),
        }
        try:
            with open(self._cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _apply_config(self) -> None:
        self.threshold_spin.setValue(float(self._cfg.get("threshold", 0.80)))
        self.hold_spin.setValue(float(self._cfg.get("hold_seconds", 1.0)))
        row = int(self._cfg.get("use_row", 1))
        rb = self.row_radios.get(max(1, min(3, row)))
        if rb:
            rb.setChecked(True)

    def _restore_window_selection(self) -> None:
        title = self._cfg.get("window_title", "")
        if title:
            idx = self.win_combo.findText(title)
            if idx >= 0:
                self.win_combo.setCurrentIndex(idx)

    def _current_use_row(self) -> int:
        for i, rb in self.row_radios.items():
            if rb.isChecked():
                return i
        return 1

    def on_use_row_changed(self) -> None:
        if self._engine is not None:
            self._engine.set_use_row(self._current_use_row())
        self._save_config()

    # ================= UI 构建 =================
    @staticmethod
    def _card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("card")
        v = QVBoxLayout(card)
        v.setContentsMargins(16, 14, 16, 14)
        v.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("sectionTitle")
            v.addWidget(lbl)
        return card, v

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ---------- 侧边栏 ----------
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(212)
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(14, 18, 14, 14)
        sv.setSpacing(6)

        logo_row = QHBoxLayout()
        logo = QLabel()
        icon_png = os.path.normpath(os.path.join(TEMPLATE_DIR, "..", "icon.png"))
        if os.path.exists(icon_png):
            logo.setPixmap(QPixmap(icon_png).scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        t1 = QLabel("北斋FGO助手")
        t1.setObjectName("appTitle")
        t2 = QLabel("HFA")
        t2.setObjectName("appSub")
        title_col.addWidget(t1)
        title_col.addWidget(t2)
        logo_row.addWidget(logo)
        logo_row.addSpacing(8)
        logo_row.addLayout(title_col, 1)
        sv.addLayout(logo_row)
        sv.addSpacing(18)

        self._nav_buttons: list[QPushButton] = []
        for idx, (name, symbol) in enumerate([("运行", "▶"), ("模板", "▦"), ("设置", "⚙"), ("日志", "☰")]):
            btn = QPushButton(f"{symbol}   {name}")
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, i=idx: self._switch_page(i))
            sv.addWidget(btn)
            self._nav_buttons.append(btn)
        self._nav_buttons[0].setChecked(True)

        sv.addStretch(1)
        ver = QLabel("v1.0 · HFA")
        ver.setObjectName("muted")
        ver.setAlignment(Qt.AlignLeft)
        sv.addWidget(ver)

        # ---------- 内容区 ----------
        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_run_page())      # 0 运行
        self._pages.addWidget(self._build_template_page()) # 1 模板
        self._pages.addWidget(self._build_settings_page()) # 2 设置
        self._pages.addWidget(self._build_log_page())      # 3 日志

        root_layout.addWidget(sidebar)
        root_layout.addWidget(self._pages, 1)
        self.setCentralWidget(root)

    def _switch_page(self, idx: int) -> None:
        self._pages.setCurrentIndex(idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == idx)

    # ---- 页 1：运行 ----
    def _build_run_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        head = QLabel("运行")
        head.setObjectName("sectionTitle")
        v.addWidget(head)

        # 状态卡
        state_card, sv = self._card()
        self.state_label = QLabel("待机")
        self.state_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {_T['muted']};")
        self.state_dot = QLabel("●")
        self.state_dot.setStyleSheet(f"color: {_T['muted']}; font-size: 14px;")
        row = QHBoxLayout()
        row.addWidget(self.state_dot)
        row.addWidget(self.state_label, 1)
        sv.addLayout(row)
        state_hint = QLabel("点击「开始」后引擎会持续监控模拟器画面，自动完成对局结束后的全部流程")
        state_hint.setObjectName("muted")
        state_hint.setWordWrap(True)
        sv.addWidget(state_hint)
        v.addWidget(state_card)

        # 目标窗口卡
        win_card, wv = self._card("目标窗口")
        win_row = QHBoxLayout()
        win_row.setSpacing(8)
        self.win_combo = QComboBox()
        win_row.addWidget(self.win_combo, 1)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_windows)
        win_row.addWidget(refresh_btn)
        wv.addLayout(win_row)
        v.addWidget(win_card)

        # 操作卡
        op_card, ov = self._card("操作")
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        self.run_btn = QPushButton("▶  开始")
        self.run_btn.setObjectName("primary")
        self.run_btn.setMinimumHeight(40)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self.on_start)
        self.stop_btn = QPushButton("■  结束")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setMinimumHeight(40)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.on_stop)
        btn_row.addWidget(self.run_btn, 1)
        btn_row.addWidget(self.stop_btn, 1)
        ov.addLayout(btn_row)
        v.addWidget(op_card)
        v.addStretch(1)
        return page

    # ---- 页 2：模板 ----
    def _build_template_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        head = QLabel("模板与助战")
        head.setObjectName("sectionTitle")
        v.addWidget(head)

        tpl_card, tv = self._card("识别模板（内置可直接用，框选可覆盖为自定义）")
        self._slot_status: dict[str, QLabel] = {}
        grid = QVBoxLayout()
        grid.setSpacing(8)
        for key, name, desc in TEMPLATE_SLOTS:
            grid.addLayout(self._slot_row(key, name, desc))
        tv.addLayout(grid)
        v.addWidget(tpl_card)

        sup_card, sv2 = self._card("助战点击位置（框选整行，点击其中心；至少录一行）")
        use_row = QHBoxLayout()
        use_row.addWidget(QLabel("使用:"))
        self.row_radios: dict[int, QRadioButton] = {}
        for i in (1, 2, 3):
            rb = QRadioButton(f"第{i}行")
            rb.setChecked(i == 1)
            rb.toggled.connect(self.on_use_row_changed)
            self.row_radios[i] = rb
            use_row.addWidget(rb)
        use_row.addStretch(1)
        sv2.addLayout(use_row)
        for i in (1, 2, 3):
            sv2.addLayout(self._slot_row(f"support_row{i}", f"助战第{i}行", "运行中可随时切换使用"))
        v.addWidget(sup_card)
        v.addStretch(1)

        scroll.setWidget(page)
        return scroll

    def _slot_row(self, key: str, name: str, desc: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(0)
        lbl = QLabel(name)
        lbl.setStyleSheet("font-weight: 600;")
        sub = QLabel(desc)
        sub.setObjectName("muted")
        sub.setStyleSheet(f"font-size: 11px; color: {_T['muted']};")
        col.addWidget(lbl)
        col.addWidget(sub)
        row.addLayout(col, 1)
        status = QLabel()
        status.setMinimumWidth(64)
        status.setAlignment(Qt.AlignCenter)
        self._slot_status[key] = status
        row.addWidget(status)
        btn = QPushButton("框选")
        btn.setFixedWidth(72)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _, k=key: self.on_record(k))
        row.addWidget(btn)
        return row

    # ---- 页 3：设置 ----
    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)

        head = QLabel("设置")
        head.setObjectName("sectionTitle")
        v.addWidget(head)

        rec_card, rv = self._card("识别参数")
        thr_row = QHBoxLayout()
        thr_lbl = QLabel("识别阈值")
        thr_lbl.setStyleSheet("font-weight: 600;")
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.5, 0.95)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setValue(0.80)
        self.threshold_spin.setFixedWidth(110)
        self.threshold_spin.valueChanged.connect(lambda _: self._save_config())
        thr_row.addWidget(thr_lbl)
        thr_row.addStretch(1)
        thr_row.addWidget(self.threshold_spin)
        rv.addLayout(thr_row)
        thr_hint = QLabel("误点别的界面就调高；该点的时候没点就调低")
        thr_hint.setObjectName("muted")
        rv.addWidget(thr_hint)

        hold_row = QHBoxLayout()
        hold_lbl = QLabel("持续秒数 n")
        hold_lbl.setStyleSheet("font-weight: 600;")
        self.hold_spin = QDoubleSpinBox()
        self.hold_spin.setRange(0.0, 10.0)
        self.hold_spin.setSingleStep(0.1)
        self.hold_spin.setValue(1.0)
        self.hold_spin.setFixedWidth(110)
        self.hold_spin.valueChanged.connect(lambda _: self._save_config())
        hold_row.addWidget(hold_lbl)
        hold_row.addStretch(1)
        hold_row.addWidget(self.hold_spin)
        rv.addLayout(hold_row)
        hold_hint = QLabel("目标需在画面上持续显示 n 秒才点击，防结算动画误触")
        hold_hint.setObjectName("muted")
        rv.addWidget(hold_hint)
        v.addWidget(rec_card)
        v.addStretch(1)
        return page

    # ---- 页 4：日志 ----
    def _build_log_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(24, 24, 24, 24)
        v.setSpacing(16)
        head = QLabel("日志")
        head.setObjectName("sectionTitle")
        v.addWidget(head)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        v.addWidget(self.log_view, 1)
        return page

    # ================= 模板录制 =================
    def current_hwnd(self) -> int | None:
        return self.win_combo.currentData()

    def _pick_region(self) -> tuple | None:
        """弹出框选（覆盖所有显示器），返回物理像素矩形 (x1,y1,x2,y2)；取消返回 None。"""
        return RegionSelector.select_region()

    def _capture_region(self, rect: tuple):
        hwnd = self.current_hwnd()
        if hwnd is None:
            QMessageBox.warning(self, "提示", "请先在「运行」页选择模拟器窗口")
            return None
        img = crop_screen_rect(hwnd, rect)
        if img is None:
            cr = get_client_rect_on_screen(hwnd)
            self.log(f"[框选失败] 选区={rect}，窗口客户区={cr}（选区必须在窗口客户区内）")
            QMessageBox.warning(self, "提示", "框选区域无效（太小）或窗口截取失败，详情见日志")
        return img

    def on_record(self, key: str) -> None:
        rect = self._pick_region()
        if rect is None:
            return
        img = self._capture_region(rect)
        if img is None:
            return
        if key.startswith("support_row"):
            # 只记录点击位置（相对窗口客户区的比例坐标）
            row = key.replace("support_row", "") or "1"
            hwnd = self.current_hwnd()
            wl, wt, wr, wb = get_client_rect_on_screen(hwnd)
            width, height = max(1, wr - wl), max(1, wb - wt)
            rx = round(((rect[0] + rect[2]) / 2 - wl) / width, 4)
            ry = round(((rect[1] + rect[3]) / 2 - wt) / height, 4)
            meta = self._load_meta()
            meta.setdefault("support_rows", {})[row] = {"rx": rx, "ry": ry}
            with open(META_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)
            self.log(f"助战第 {row} 行点击位置已保存: 比例坐标 ({rx}, {ry})")
        else:
            path = os.path.join(TEMPLATE_DIR, f"{key}.png")
            cv2.imwrite(path, img)
            self.log(f"模板已保存: {path} ({img.shape[1]}x{img.shape[0]})")
        self._refresh_template_status()

    def _load_meta(self) -> dict:
        if os.path.exists(META_PATH):
            try:
                with open(META_PATH, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                # 兼容旧版单行字段
                if "support_row" in meta:
                    meta.setdefault("support_rows", {}).setdefault("1", meta["support_row"])
                return meta
            except Exception:
                pass
        return {}

    def _support_rows(self) -> dict:
        return self._load_meta().get("support_rows", {})

    def _refresh_template_status(self) -> None:
        t = _T
        rows = self._support_rows()
        for key, _, _ in TEMPLATE_SLOTS:
            label = self._slot_status[key]
            user = os.path.exists(os.path.join(TEMPLATE_DIR, f"{key}.png"))
            builtin = os.path.exists(os.path.join(TEMPLATE_DIR, "builtin", f"{key}.png"))
            if user:
                label.setText("自定义")
                label.setStyleSheet(f"color: {t['success']}; font-weight: 700;")
            elif builtin:
                label.setText("内置")
                label.setStyleSheet(f"color: {t['builtin']}; font-weight: 700;")
            else:
                label.setText("未录制")
                label.setStyleSheet(f"color: {t['danger']}; font-weight: 700;")
        for i in (1, 2, 3):
            label = self._slot_status[f"support_row{i}"]
            if str(i) in rows:
                label.setText("已录入")
                label.setStyleSheet(f"color: {t['success']}; font-weight: 700;")
            else:
                label.setText("需录入")
                label.setStyleSheet(f"color: {t['danger']}; font-weight: 700;")

    def _set_state(self, text: str, color: str) -> None:
        self.state_label.setText(text)
        self.state_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {color};")
        self.state_dot.setStyleSheet(f"color: {color}; font-size: 14px;")

    # ================= 开始 / 结束 =================
    def on_start(self) -> None:
        hwnd = self.current_hwnd()
        if hwnd is None:
            self.refresh_windows()
            hwnd = self._pick_window_dialog()
            if hwnd is None:
                return
            idx = self.win_combo.findData(hwnd)
            if idx >= 0:
                self.win_combo.setCurrentIndex(idx)

        use_row = self._current_use_row()
        if str(use_row) not in self._support_rows():
            QMessageBox.warning(
                self, "缺少助战位置",
                f"当前选择的「第{use_row}行」尚未框选录入。\n"
                "请先在「模板」页的「助战第" + str(use_row) + "行」处点「框选」选取整行，"
                "或切换到已录入的行。",
            )
            return

        self.log(f"[启动] 目标窗口: {self.win_combo.currentText()}")
        self._engine = FgoEngine(
            hwnd, TEMPLATE_DIR,
            threshold=self.threshold_spin.value(),
            hold_seconds=self.hold_spin.value(),
        )
        self._engine.use_row = use_row
        self._engine.log_signal.connect(self.log)
        self._engine.state_signal.connect(self._on_engine_state)
        self._engine.finished_ok.connect(self.on_engine_finished)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._set_state("运行中", _T["success"])
        self._engine.start()

    def _on_engine_state(self, text: str) -> None:
        self.state_label.setText(text)
        self.state_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {_T['text']};"
        )
        self.state_dot.setStyleSheet(f"color: {_T['primary']}; font-size: 14px;")

    def _pick_window_dialog(self) -> int | None:
        """开始时未选窗口则弹窗选择。"""
        dlg = QDialog(self)
        dlg.setWindowTitle("HFA - 选择模拟器窗口")
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("请选择 FGO 所在的模拟器窗口:"))
        combo = QComboBox()
        for hwnd, title in list_windows():
            combo.addItem(title, hwnd)
        v.addWidget(combo)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        v.addWidget(buttons)
        if dlg.exec() == QDialog.Accepted and combo.currentData() is not None:
            return combo.currentData()
        return None

    def on_stop(self) -> None:
        if self._engine is not None:
            self._engine.stop()
            self._set_state("停止中…", _T["danger"])
            self.log("[用户] 已请求结束，等待引擎退出…")

    def on_engine_finished(self, _ok: bool) -> None:
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._engine = None
        self._set_state("待机", _T["muted"])
        self.log("[结束] 引擎已退出")

    # ================= 窗口 / 日志 =================
    def refresh_windows(self) -> None:
        cur = self.current_hwnd()
        self.win_combo.clear()
        for hwnd, title in list_windows():
            self.win_combo.addItem(title, hwnd)
        if cur is not None:
            idx = self.win_combo.findData(cur)
            if idx >= 0:
                self.win_combo.setCurrentIndex(idx)

    def log(self, msg: str) -> None:
        self.log_view.appendPlainText(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def closeEvent(self, event) -> None:  # noqa: N802
        self._save_config()
        if self._engine is not None:
            self._engine.stop()
            self._engine.wait(2000)
        super().closeEvent(event)
