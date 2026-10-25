"""北斋FGO助手 - 主界面 v2（无边框一体化窗口 + 自定义标题栏 + 侧边栏功能区）。

布局参考成熟桌面产品：
- 自绘标题栏（logo + 拖拽区 + 最小化/最大化/关闭），Win11 下 DWM 圆角
- 侧边栏：「功能菜单」分组放功能名（自动结算），底部放设置/日志与版本号
- 内容区：英雄卡（运行控制）+ 模板管理卡 + 助战位置卡
战斗本体由玩家手动打，打完引擎自动接管结算流程。
"""
from __future__ import annotations

import ctypes
import json
import math
import os
import sys
import time

import cv2
from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QApplication,
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
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from .capture import crop_screen_rect, get_client_rect_on_screen, list_windows
from .fgo_engine import FgoEngine
from .friend_engine import FriendEngine
from .region_selector import RegionSelector

if getattr(sys, "frozen", False):  # PyInstaller 打包后，资源放 exe 旁边，方便用户修改
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_DIR = os.path.join(BASE_DIR, "assets", "templates")
META_PATH = os.path.join(TEMPLATE_DIR, "meta.json")
FONT_STACK = "'HarmonyOS Sans SC', 'HarmonyOS Sans', 'Microsoft YaHei UI'"

# (key, 名称, 说明)；助战行位置单独处理
TEMPLATE_SLOTS = [
    ("battle_result", "「战斗结果」标题", "结算页识别，点屏幕正中央"),
    ("tap_start", "「请点击游戏界面」", "点屏幕正中央"),
    ("next", "「下一步」按钮", "点击识别位置"),
    ("attack", "「连续出击」按钮", "点击识别位置"),
    ("apple", "黄金果实行", "没体力时自动补体力（可选）"),
    ("confirm", "「决定」按钮", "补体力确认弹窗（可选）"),
    ("support_title", "「助战选择」标题", "识别助战界面"),
]

# 友情召唤页模板槽位（内置模板已随包提供，框选可覆盖）
FRIEND_SLOTS = [
    ("friend_summon", "「友情点召唤」画面", "识别到后点「召唤 x100」"),
    ("friend_x100", "「召唤 x100」按钮", "点击其识别位置"),
    ("friend_confirm", "「决定」弹窗按钮", "x100 与 继续召唤 共用"),
    ("friend_continue", "「继续进行100次召唤」", "点击进入下一轮循环"),
    ("friend_stop", "停止用素材图", "出现即自动停止（可选）"),
]
FRIEND_REQUIRED = ("friend_summon", "friend_confirm", "friend_continue")

# ============ 主题 token（Apple HIG 暗色 + 品牌紫） ============
_T = {
    "bg_top":     "#141422",
    "bg_bottom":  "#0C0C18",
    "sidebar":    "rgba(255, 255, 255, 0.03)",
    "glass":      "rgba(32, 32, 50, 0.55)",
    "sep":        "rgba(255, 255, 255, 0.07)",
    "fill":       "rgba(120, 120, 128, 0.22)",
    "primary":    "#6C63FF",
    "primary_h":  "#7D75FF",
    "text":       "#F0F0F8",
    "label2":     "rgba(235, 235, 245, 0.62)",
    "label3":     "rgba(235, 235, 245, 0.35)",
    "success":    "#3ECFCF",
    "danger":     "#FF6584",
    "builtin":    "#7B9DFF",
    "icon":       "#C9C9DE",
}

# ============ SVG 图标（feather 风格，统一 2px 圆头描边） ============
_ICON_PATHS = {
    "play": '<polygon points="6 4 20 12 6 20 6 4"/>',
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
    "log": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/>',
    "refresh": '<polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>',
    "crop": '<path d="M6.13 1L6 16a2 2 0 0 0 2 2h15"/><path d="M1 6.13L16 6a2 2 0 0 1 2 2v15"/>',
    "min": '<line x1="5" y1="12" x2="19" y2="12"/>',
    "max": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "restore": '<rect x="4" y="8" width="12" height="12" rx="2"/><polyline points="8 4 18 4 18 14"/>',
    "close": '<line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>',
    "collapse": '<polyline points="15 6 9 12 15 18"/>',
    "expand": '<polyline points="9 6 15 12 9 18"/>',
    "repeat": '<polyline points="17 1 21 5 17 9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/><polyline points="7 23 3 19 7 15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>',
}


def _render_mult() -> int:
    """图标/位图超采样倍数：跟随屏幕实际 devicePixelRatio（至少 2x），
    否则在 125%/150% 缩放下位图被二次缩放，看起来发糊。"""
    scr = QApplication.primaryScreen()
    dpr = scr.devicePixelRatio() if scr else 1.0
    return max(2, math.ceil(dpr))


def svg_icon(name: str, color: str, size: int = 18) -> QIcon:
    body = _ICON_PATHS[name]
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        f'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )
    renderer = QSvgRenderer(bytearray(svg.encode("utf-8")))
    mult = _render_mult()
    pm = QPixmap(size * mult, size * mult)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter, QRect(0, 0, size * mult, size * mult))
    painter.end()
    pm.setDevicePixelRatio(float(mult))
    return QIcon(pm)


def _dpr_pixmap(path: str, size: int) -> QPixmap:
    """按屏幕 devicePixelRatio 加载位图，避免高分屏下发糊。"""
    src = QPixmap(path)
    mult = _render_mult()
    out = src.scaled(size * mult, size * mult,
                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
    out.setDevicePixelRatio(float(mult))
    return out


def build_stylesheet() -> str:
    t = _T
    return f"""
    QWidget {{ color: {t['text']}; font-size: 13px;
               font-family: {FONT_STACK}; }}
    #root {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {t['bg_top']}, stop:1 {t['bg_bottom']});
    }}
    QLabel#pageTitle {{ font-size: 20px; font-weight: 700; }}
    QLabel#sectionTitle {{ font-size: 14px; font-weight: 700; }}
    QLabel#muted {{ color: {t['label2']}; }}
    QLabel#hint {{ color: {t['label3']}; font-size: 12px; }}
    QLabel#caption {{ color: {t['label3']}; font-size: 10px; letter-spacing: 2px; }}

    /* ---------- 侧边栏 ---------- */
    #sidebar {{
        background: rgba(255, 255, 255, 0.035);
        border: 1px solid {t['sep']};
        border-radius: 16px;
    }}
    QLabel#appTitle {{ font-size: 15px; font-weight: 700; }}
    QLabel#appSub {{ font-size: 9px; color: {t['label3']}; letter-spacing: 3px; }}
    QPushButton#nav {{
        text-align: left; padding: 0 12px; min-height: 38px;
        border: none; border-radius: 10px; background: transparent;
        color: {t['label2']}; font-size: 13px; font-weight: 600;
    }}
    QPushButton#nav:hover {{ background: rgba(255, 255, 255, 0.06); color: {t['text']}; }}
    QPushButton#nav:checked {{
        background: rgba(108, 99, 255, 0.18); color: {t['text']};
        border-left: 3px solid {t['primary']}; padding-left: 9px;
    }}
    /* 折叠态：隐藏文字，图标居中 */
    QPushButton#nav[collapsed="true"] {{ text-align: center; padding: 0; }}
    QPushButton#nav[collapsed="true"]:checked {{
        border-left: none; padding: 0;
        background: rgba(108, 99, 255, 0.18); color: {t['text']};
    }}

    /* ---------- 标题栏 ---------- */
    #titlebar {{ background: transparent; }}
    QLabel#tbTitle {{ font-size: 12px; font-weight: 600; color: {t['label2']}; }}
    QPushButton#winbtn {{
        background: transparent; border: none; border-radius: 0;
        min-height: 40px; max-height: 40px; padding: 0; min-width: 44px;
    }}
    QPushButton#winbtn:hover {{ background: rgba(255, 255, 255, 0.08); }}
    QPushButton#winclose:hover {{ background: #E81123; }}

    /* ---------- 卡片 ---------- */
    QFrame#card {{
        background: {t['glass']};
        border: 1px solid {t['sep']};
        border-radius: 16px;
    }}
    QFrame#iconTile {{
        background: rgba(108, 99, 255, 0.16);
        border: 1px solid rgba(108, 99, 255, 0.35);
        border-radius: 12px;
    }}

    /* ---------- 控件 ---------- */
    QPushButton {{
        background: {t['fill']}; color: {t['text']}; border: none;
        border-radius: 10px; padding: 0 16px; min-height: 36px; font-weight: 600;
    }}
    QPushButton:hover {{ background: rgba(120, 120, 128, 0.32); }}
    QPushButton:pressed {{ background: rgba(120, 120, 128, 0.28); }}
    QPushButton:disabled {{ color: {t['label3']}; background: rgba(120, 120, 128, 0.12); }}
    QPushButton#primary {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #7D75FF, stop:1 #6C63FF);
        color: white; min-height: 42px; border-radius: 12px;
        font-size: 14px; font-weight: 700;
    }}
    QPushButton#primary:hover {{ background: {t['primary_h']}; }}
    QPushButton#primary:disabled {{
        background: rgba(108, 99, 255, 0.30); color: rgba(255,255,255,0.55);
    }}
    QPushButton#danger {{
        background: rgba(255, 101, 132, 0.12); color: {t['danger']};
        min-height: 42px; border-radius: 12px; font-size: 14px; font-weight: 700;
    }}
    QPushButton#danger:hover {{ background: rgba(255, 101, 132, 0.22); }}
    QPushButton#danger:disabled {{ color: {t['label3']}; background: rgba(120,120,128,0.12); }}
    QPushButton#ghost {{
        background: transparent; min-height: 36px; font-weight: 600; color: {t['label2']};
    }}
    QPushButton#ghost:hover {{ color: {t['text']}; background: rgba(255,255,255,0.06); }}

    QComboBox, QDoubleSpinBox {{
        background: {t['fill']}; border: none;
        border-radius: 10px; min-height: 36px; padding: 0 10px; color: {t['text']};
    }}
    QComboBox:hover, QDoubleSpinBox:hover {{ background: rgba(120, 120, 128, 0.32); }}
    QComboBox::drop-down {{ border: none; width: 26px; }}
    QComboBox QAbstractItemView {{
        background: #1C1C2E; border: 1px solid {t['sep']};
        border-radius: 10px; selection-background-color: rgba(108,99,255,0.35);
        outline: none;
    }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 18px; }}

    QRadioButton {{ spacing: 6px; }}
    QRadioButton::indicator {{
        width: 14px; height: 14px; border-radius: 7px;
        border: 1px solid {t['label2']}; background: transparent;
    }}
    QRadioButton::indicator:hover {{ border-color: {t['primary']}; }}
    QRadioButton::indicator:checked {{
        border: 4px solid {t['primary']}; background: white;
    }}

    QPlainTextEdit#log {{
        background: {t['glass']}; border: 1px solid {t['sep']};
        border-radius: 16px; padding: 12px;
        font-family: 'Consolas', 'Cascadia Mono', monospace; font-size: 12px; color: #C8C8DE;
    }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.14); border-radius: 4px; min-height: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    """


def _enable_round_corners(hwnd: int) -> None:
    """Win11 圆角（frameless 窗口默认直角，用 DWM 打开）。"""
    try:
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), 4)
    except Exception:
        pass


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("北斋FGO助手 HokusaiFGOAssistant (HFA)")
        icon_png = os.path.normpath(os.path.join(TEMPLATE_DIR, "..", "icon.png"))
        if os.path.exists(icon_png):
            self.setWindowIcon(QIcon(icon_png))
        self.resize(1000, 680)
        self.setMinimumSize(880, 620)
        self.setWindowFlag(Qt.FramelessWindowHint)
        self.setMouseTracking(True)

        os.makedirs(TEMPLATE_DIR, exist_ok=True)
        self._engine: FgoEngine | None = None
        self._friend_engine: FriendEngine | None = None
        self._cfg_path = os.path.join(BASE_DIR, "config.json")
        self._cfg = self._load_config()
        self._drag_pos = None
        self._resize_edge = ""

        self.setStyleSheet(build_stylesheet())
        self._build_ui()
        self._apply_config()
        self.refresh_windows()
        self._restore_window_selection()
        self._refresh_template_status()
        self._center_on_screen()

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.x() + (screen.width() - self.width()) // 2,
            screen.y() + (screen.height() - self.height()) // 2,
        )

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        QTimer.singleShot(0, lambda: _enable_round_corners(int(self.winId())))

    # ================= 无边框：拖拽 / 双击最大化 / 边缘缩放 =================
    def _hit_edge(self, pos) -> str:
        if self.isMaximized():
            return ""
        m, r = 6, self.rect()
        edge = ""
        if pos.x() <= m:
            edge += "L"
        if pos.x() >= r.width() - m:
            edge += "R"
        if pos.y() <= m:
            edge += "T"
        if pos.y() >= r.height() - m:
            edge += "B"
        return edge

    _EDGE_CURSORS = {"L": Qt.SizeHorCursor, "R": Qt.SizeHorCursor,
                     "T": Qt.SizeVerCursor, "B": Qt.SizeVerCursor,
                     "TL": Qt.SizeFDiagCursor, "BR": Qt.SizeFDiagCursor,
                     "TR": Qt.SizeBDiagCursor, "BL": Qt.SizeBDiagCursor}

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._resize_edge = self._hit_edge(event.position().toPoint())
            if self._resize_edge:
                self._drag_geo = self.frameGeometry()
                self._drag_mouse = event.globalPosition().toPoint()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if self._resize_edge and event.buttons() & Qt.LeftButton:
            d = event.globalPosition().toPoint() - self._drag_mouse
            g = QRect(self._drag_geo)
            if "L" in self._resize_edge:
                g.setLeft(g.left() + d.x())
            if "R" in self._resize_edge:
                g.setRight(g.right() + d.x())
            if "T" in self._resize_edge:
                g.setTop(g.top() + d.y())
            if "B" in self._resize_edge:
                g.setBottom(g.bottom() + d.y())
            if g.width() >= self.minimumWidth() and g.height() >= self.minimumHeight():
                self.setGeometry(g)
            return
        edge = self._hit_edge(pos)
        self.setCursor(self._EDGE_CURSORS.get(edge, Qt.ArrowCursor))
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        self._resize_edge = ""
        super().mouseReleaseEvent(event)

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
            "friend_window_title": self.friend_combo.currentText(),
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
        ftitle = self._cfg.get("friend_window_title", "")
        if ftitle:
            idx = self.friend_combo.findText(ftitle)
            if idx >= 0:
                self.friend_combo.setCurrentIndex(idx)

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
        # 注意：不要给卡片加 QGraphicsDropShadowEffect —— 它会把整个组件
        # 拉进位图渲染路径，导致卡片内所有文字发虚。分层感靠边线和底色。
        v = QVBoxLayout(card)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)
        if title:
            lbl = QLabel(title)
            lbl.setObjectName("sectionTitle")
            v.addWidget(lbl)
        return card, v

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._build_titlebar())
        body = QHBoxLayout()
        body.setContentsMargins(10, 10, 0, 10)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        self._pages = QStackedWidget()
        self._pages.addWidget(self._build_main_page())    # 0 自动结算（运行+模板）
        self._pages.addWidget(self._build_settings_page())  # 1 设置
        self._pages.addWidget(self._build_log_page())       # 2 日志
        self._pages.addWidget(self._build_friend_page())  # 3 友情召唤
        body.addWidget(self._pages, 1)
        rl.addLayout(body, 1)
        self.setCentralWidget(root)

    # ---- 标题栏 ----
    def _build_titlebar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("titlebar")
        bar.setFixedHeight(44)
        h = QHBoxLayout(bar)
        h.setContentsMargins(14, 0, 0, 0)
        h.setSpacing(8)

        icon_png = os.path.normpath(os.path.join(TEMPLATE_DIR, "..", "icon.png"))
        logo = QLabel()
        if os.path.exists(icon_png):
            logo.setPixmap(_dpr_pixmap(icon_png, 22))
        h.addWidget(logo)
        h.addStretch(1)

        def win_btn(name: str, icon: str, cls: str = "winbtn") -> QPushButton:
            btn = QPushButton()
            btn.setObjectName(cls)
            btn.setFixedSize(44, 40)
            btn.setIcon(svg_icon(icon, _T["icon"], 14))
            btn.setCursor(Qt.PointingHandCursor)
            return btn

        self._btn_min = win_btn("min", "min")
        self._btn_min.clicked.connect(self.showMinimized)
        self._btn_max = win_btn("max", "max")
        self._btn_max.clicked.connect(self._toggle_max)
        self._btn_close = win_btn("close", "close", "winclose")
        self._btn_close.clicked.connect(self.close)
        for b in (self._btn_min, self._btn_max, self._btn_close):
            h.addWidget(b)

        # 拖拽移动 / 双击最大化
        self._tb_pressed = False

        def tb_press(ev):
            if ev.button() == Qt.LeftButton:
                self._tb_pressed = True
                self._tb_drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

        def tb_move(ev):
            if self._tb_pressed and not self.isMaximized():
                self.move(ev.globalPosition().toPoint() - self._tb_drag)

        def tb_release(_):
            self._tb_pressed = False

        def tb_dblclick(ev):
            if ev.button() == Qt.LeftButton:
                self._toggle_max()

        bar.mousePressEvent = tb_press
        bar.mouseMoveEvent = tb_move
        bar.mouseReleaseEvent = tb_release
        bar.mouseDoubleClickEvent = tb_dblclick
        return bar

    def _toggle_max(self) -> None:
        if self.isMaximized():
            self.showNormal()
            self._btn_max.setIcon(svg_icon("max", _T["icon"], 14))
        else:
            self.showMaximized()
            self._btn_max.setIcon(svg_icon("restore", _T["icon"], 14))

    # ---- 侧边栏（悬浮岛，可折叠） ----
    SIDEBAR_W_EXPAND = 216
    SIDEBAR_W_COLLAPSE = 64

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(self.SIDEBAR_W_EXPAND)
        self._sidebar = sidebar
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(12, 16, 12, 12)
        sv.setSpacing(4)

        # 顶部：logo + 标题 + 折叠按钮（折叠时整体隐藏，由展开按钮接管）
        logo_row = QHBoxLayout()
        logo_row.setSpacing(10)
        self._logo = QLabel()
        icon_png = os.path.normpath(os.path.join(TEMPLATE_DIR, "..", "icon.png"))
        if os.path.exists(icon_png):
            self._logo.setPixmap(_dpr_pixmap(icon_png, 32))
        logo_row.addWidget(self._logo)
        col = QVBoxLayout()
        col.setSpacing(0)
        self._app_title = QLabel("北斋FGO助手")
        self._app_title.setObjectName("appTitle")
        self._app_sub = QLabel("HFA")
        self._app_sub.setObjectName("appSub")
        col.addWidget(self._app_title)
        col.addWidget(self._app_sub)
        logo_row.addLayout(col, 1)
        self._btn_collapse = QPushButton()
        self._btn_collapse.setObjectName("ghost")
        self._btn_collapse.setFixedSize(28, 28)
        self._btn_collapse.setIcon(svg_icon("collapse", _T["icon"], 14))
        self._btn_collapse.setCursor(Qt.PointingHandCursor)
        self._btn_collapse.setToolTip("收起侧边栏")
        self._btn_collapse.clicked.connect(self._toggle_sidebar)
        logo_row.addWidget(self._btn_collapse)
        sv.addLayout(logo_row)

        # 折叠态：顶部居中的展开按钮（64px 宽度下 logo 行放不下，换成单按钮）
        self._btn_expand = QPushButton()
        self._btn_expand.setObjectName("ghost")
        self._btn_expand.setFixedSize(28, 28)
        self._btn_expand.setIcon(svg_icon("expand", _T["icon"], 14))
        self._btn_expand.setCursor(Qt.PointingHandCursor)
        self._btn_expand.setToolTip("展开侧边栏")
        self._btn_expand.clicked.connect(self._toggle_sidebar)
        self._btn_expand.setVisible(False)
        sv.addWidget(self._btn_expand, 0, Qt.AlignHCenter)
        sv.addSpacing(16)

        self._caption = QLabel("功能菜单")
        self._caption.setObjectName("caption")
        sv.addWidget(self._caption)
        sv.addSpacing(4)

        self._nav_buttons: dict[int, QPushButton] = {}
        self._nav_text: dict[int, str] = {
            0: "自动结算", 1: "设置", 2: "日志", 3: "友情召唤",
        }
        # 顶部：主功能（idx 与页面索引一致）
        for idx, icon in ((0, "play"), (3, "repeat")):
            self._nav_buttons[idx] = self._make_nav_btn(
                sv, idx, self._nav_text[idx], icon)
        self._nav_buttons[0].setChecked(True)

        sv.addStretch(1)

        # 底部：设置 / 日志 + 版本号
        for idx, icon in ((1, "settings"), (2, "log")):
            self._nav_buttons[idx] = self._make_nav_btn(
                sv, idx, self._nav_text[idx], icon)
        sv.addSpacing(8)
        self._ver_label = QLabel(f"v{__version__}")
        self._ver_label.setObjectName("caption")
        sv.addWidget(self._ver_label)

        # 折叠动画
        from PySide6.QtCore import (
            QPropertyAnimation, QEasingCurve, QParallelAnimationGroup,
        )
        self._sidebar_anim = QParallelAnimationGroup(self)
        for prop in (b"minimumWidth", b"maximumWidth"):
            anim = QPropertyAnimation(sidebar, prop, self)
            anim.setDuration(180)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            self._sidebar_anim.addAnimation(anim)
        return sidebar

    def _toggle_sidebar(self) -> None:
        self._collapsed = not getattr(self, "_collapsed", False)
        target = self.SIDEBAR_W_COLLAPSE if self._collapsed else self.SIDEBAR_W_EXPAND
        self._sidebar_anim.stop()
        for i in range(self._sidebar_anim.animationCount()):
            self._sidebar_anim.animationAt(i).setEndValue(target)
        self._sidebar_anim.start()

        # 文字元素显隐
        show = not self._collapsed
        for idx, btn in self._nav_buttons.items():
            btn.setText(self._nav_text[idx] if show else "")
            btn.setToolTip("" if show else self._nav_text[idx])
            # 切换 QSS 属性选择器：折叠态图标居中
            btn.setProperty("collapsed", not show)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        for w in (self._logo, self._app_title, self._app_sub,
                  self._caption, self._ver_label, self._btn_collapse):
            w.setVisible(show)
        self._btn_expand.setVisible(not show)

    def _make_nav_btn(self, layout: QVBoxLayout, idx: int, name: str, icon: str) -> QPushButton:
        btn = QPushButton(svg_icon(icon, _T["icon"], 16), name)
        btn.setObjectName("nav")
        btn.setIconSize(QSize(16, 16))
        btn.setCheckable(True)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _, i=idx: self._switch_page(i))
        layout.addWidget(btn)
        return btn

    def _switch_page(self, idx: int) -> None:
        self._pages.setCurrentIndex(idx)
        for i, btn in self._nav_buttons.items():
            btn.setChecked(i == idx)

    # ---- 页 0：自动结算（英雄卡 + 模板 + 助战） ----
    def _build_main_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 26)
        v.setSpacing(16)

        # 英雄卡：运行控制
        hero, hv = self._card()
        hv.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(14)
        tile = QFrame()
        tile.setObjectName("iconTile")
        tile.setFixedSize(46, 46)
        tile_lay = QVBoxLayout(tile)
        tile_lay.setContentsMargins(0, 0, 0, 0)
        tile_icon = QLabel()
        tile_icon.setPixmap(svg_icon("play", _T["primary"], 22).pixmap(22, 22))
        tile_icon.setAlignment(Qt.AlignCenter)
        tile_lay.addWidget(tile_icon)
        top.addWidget(tile)
        top.addSpacing(2)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t = QLabel("自动结算")
        t.setStyleSheet("font-size: 17px; font-weight: 700;")
        self.state_label = QLabel("待机")
        self.state_label.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {_T['label2']};")
        title_col.addWidget(t)
        title_col.addWidget(self.state_label)
        top.addLayout(title_col, 1)
        hv.addLayout(top)

        ctl = QHBoxLayout()
        ctl.setSpacing(8)
        self.win_combo = QComboBox()
        self.win_combo.setMinimumWidth(220)
        ctl.addWidget(self.win_combo, 1)
        refresh_btn = QPushButton()
        refresh_btn.setObjectName("ghost")
        refresh_btn.setIcon(svg_icon("refresh", _T["icon"], 15))
        refresh_btn.setFixedWidth(38)
        refresh_btn.setToolTip("刷新窗口列表")
        refresh_btn.clicked.connect(self.refresh_windows)
        ctl.addWidget(refresh_btn)
        self.run_btn = QPushButton("开始")
        self.run_btn.setObjectName("primary")
        self.run_btn.setIcon(svg_icon("play", "#FFFFFF", 14))
        self.run_btn.setMinimumWidth(120)
        self.run_btn.setCursor(Qt.PointingHandCursor)
        self.run_btn.clicked.connect(self.on_start)
        self.stop_btn = QPushButton("结束")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setMinimumWidth(100)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setCursor(Qt.PointingHandCursor)
        self.stop_btn.clicked.connect(self.on_stop)
        ctl.addWidget(self.run_btn)
        ctl.addWidget(self.stop_btn)
        hv.addLayout(ctl)
        v.addWidget(hero)

        # 模板卡 + 助战卡（左右两列）
        row = QHBoxLayout()
        row.setSpacing(16)

        tpl_card, tv = self._card("识别模板")
        tpl_hint = QLabel("内置模板可直接使用，框选可覆盖为自定义")
        tpl_hint.setObjectName("hint")
        tv.addWidget(tpl_hint)
        self._slot_status: dict[str, QLabel] = {}
        for key, name, desc in TEMPLATE_SLOTS:
            tv.addLayout(self._slot_row(key, name, desc))

        sup_card, sv2 = self._card("助战位置")
        sv2.setSpacing(10)
        sup_hint = QLabel("框选要点的整行，点击其中心；至少录一行")
        sup_hint.setObjectName("hint")
        sv2.addWidget(sup_hint)
        use_row = QHBoxLayout()
        use_row.setSpacing(10)
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
            sv2.addLayout(self._slot_row(f"support_row{i}", f"助战第{i}行", "运行中可随时切换"))
        sv2.addStretch(1)  # 多余高度全部压到卡片底部，内容保持顶部紧凑
        row.addWidget(tpl_card, 3)
        row.addWidget(sup_card, 2)
        v.addLayout(row, 1)
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
        sub.setObjectName("hint")
        col.addWidget(lbl)
        col.addWidget(sub)
        row.addLayout(col, 1)
        status = QLabel()
        status.setMinimumWidth(56)
        status.setAlignment(Qt.AlignCenter)
        self._slot_status[key] = status
        row.addWidget(status)
        btn = QPushButton(svg_icon("crop", _T["icon"], 14), "框选")
        btn.setFixedWidth(84)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(lambda _, k=key: self.on_record(k))
        row.addWidget(btn)
        return row

    # ---- 页 1：设置 ----
    def _build_settings_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 26)
        v.setSpacing(16)
        head = QLabel("设置")
        head.setObjectName("pageTitle")
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
        thr_hint.setObjectName("hint")
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
        hold_hint.setObjectName("hint")
        rv.addWidget(hold_hint)
        v.addWidget(rec_card)
        v.addStretch(1)
        return page

    # ---- 页 2：日志 ----
    def _build_log_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 26)
        v.setSpacing(16)
        head = QLabel("日志")
        head.setObjectName("pageTitle")
        v.addWidget(head)
        self.log_view = QPlainTextEdit()
        self.log_view.setObjectName("log")
        self.log_view.setReadOnly(True)
        v.addWidget(self.log_view, 1)
        return page

    # ---- 页 3：友情召唤 ----
    def _build_friend_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(26, 22, 26, 26)
        v.setSpacing(16)

        # 英雄卡：运行控制
        hero, hv = self._card()
        hv.setSpacing(12)
        top = QHBoxLayout()
        top.setSpacing(14)
        tile = QFrame()
        tile.setObjectName("iconTile")
        tile.setFixedSize(46, 46)
        tile_lay = QVBoxLayout(tile)
        tile_lay.setContentsMargins(0, 0, 0, 0)
        tile_icon = QLabel()
        tile_icon.setPixmap(svg_icon("repeat", _T["primary"], 22).pixmap(22, 22))
        tile_icon.setAlignment(Qt.AlignCenter)
        tile_lay.addWidget(tile_icon)
        top.addWidget(tile)
        top.addSpacing(2)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t = QLabel("友情召唤")
        t.setStyleSheet("font-size: 17px; font-weight: 700;")
        self.friend_state_label = QLabel("待机")
        self.friend_state_label.setStyleSheet(
            f"font-size: 12px; font-weight: 600; color: {_T['label2']};")
        title_col.addWidget(t)
        title_col.addWidget(self.friend_state_label)
        top.addLayout(title_col, 1)
        hv.addLayout(top)

        ctl = QHBoxLayout()
        ctl.setSpacing(8)
        self.friend_combo = QComboBox()
        self.friend_combo.setMinimumWidth(220)
        self.friend_combo.currentTextChanged.connect(lambda _: self._save_config())
        ctl.addWidget(self.friend_combo, 1)
        frefresh_btn = QPushButton()
        frefresh_btn.setObjectName("ghost")
        frefresh_btn.setIcon(svg_icon("refresh", _T["icon"], 15))
        frefresh_btn.setFixedWidth(38)
        frefresh_btn.setToolTip("刷新窗口列表")
        frefresh_btn.clicked.connect(self.refresh_friend_windows)
        ctl.addWidget(frefresh_btn)
        self.friend_run_btn = QPushButton("开始")
        self.friend_run_btn.setObjectName("primary")
        self.friend_run_btn.setIcon(svg_icon("play", "#FFFFFF", 14))
        self.friend_run_btn.setMinimumWidth(120)
        self.friend_run_btn.setCursor(Qt.PointingHandCursor)
        self.friend_run_btn.clicked.connect(self.on_friend_start)
        self.friend_stop_btn = QPushButton("结束")
        self.friend_stop_btn.setObjectName("danger")
        self.friend_stop_btn.setMinimumWidth(100)
        self.friend_stop_btn.setEnabled(False)
        self.friend_stop_btn.setCursor(Qt.PointingHandCursor)
        self.friend_stop_btn.clicked.connect(self.on_friend_stop)
        ctl.addWidget(self.friend_run_btn)
        ctl.addWidget(self.friend_stop_btn)
        hv.addLayout(ctl)
        v.addWidget(hero)

        # 模板卡
        tpl_card, tv = self._card("召唤模板")
        tpl_hint = QLabel("先手动进入友情点召唤界面再点「开始」；循环中可随时点「结束」")
        tpl_hint.setObjectName("hint")
        tv.addWidget(tpl_hint)
        for key, name, desc in FRIEND_SLOTS:
            tv.addLayout(self._slot_row(key, name, desc))
        v.addWidget(tpl_card)
        v.addStretch(1)
        scroll.setWidget(page)
        return scroll

    # ---- 友情召唤：启停 ----
    def on_friend_start(self) -> None:  # noqa: N802
        hwnd = self.friend_combo.currentData()
        if hwnd is None:
            self.refresh_friend_windows()
            hwnd = self.friend_combo.currentData()
        if hwnd is None:
            QMessageBox.warning(self, "提示", "请先选择 FGO 所在的模拟器窗口")
            return

        def tpl_ready(key: str) -> bool:
            return (
                os.path.exists(os.path.join(TEMPLATE_DIR, f"{key}.png"))
                or os.path.exists(os.path.join(TEMPLATE_DIR, "builtin", f"{key}.png"))
            )

        labels = {k: n for k, n, _ in FRIEND_SLOTS}
        missing = [labels[k] for k in FRIEND_REQUIRED if not tpl_ready(k)]
        x100 = self._load_meta().get("friend_x100") or {}
        if not tpl_ready("friend_x100") and \
                not (isinstance(x100, dict) and "rx" in x100 and "ry" in x100):
            missing.append("「召唤 x100」按钮")
        if missing:
            QMessageBox.warning(
                self, "缺少模板/位置",
                "以下内容尚未录制，请先在下方框选：\n· " + "\n· ".join(missing))
            return
        if not tpl_ready("friend_stop"):
            self.log("[友情召唤] 提示：未设置停止素材图，将一直循环直到手动「结束」")

        self.log(f"[友情召唤启动] 目标窗口: {self.friend_combo.currentText()}")
        self._friend_engine = FriendEngine(
            hwnd, TEMPLATE_DIR, threshold=self.threshold_spin.value())
        self._friend_engine.log_signal.connect(self.log)
        self._friend_engine.state_signal.connect(self._on_friend_state)
        self._friend_engine.finished_ok.connect(self.on_friend_finished)
        self.friend_run_btn.setEnabled(False)
        self.friend_stop_btn.setEnabled(True)
        self._set_friend_state("运行中", _T["success"])
        self._friend_engine.start()

    def on_friend_stop(self) -> None:  # noqa: N802
        if self._friend_engine is not None:
            self._friend_engine.stop()
            self._set_friend_state("停止中…", _T["danger"])
            self.log("[用户] 已请求结束友情召唤…")

    def _on_friend_state(self, text: str) -> None:
        self.friend_state_label.setText(text)
        self.friend_state_label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {_T['text']};"
        )

    def on_friend_finished(self, _ok: bool) -> None:
        self.friend_run_btn.setEnabled(True)
        self.friend_stop_btn.setEnabled(False)
        self._friend_engine = None
        self._set_friend_state("待机", _T["label2"])
        self.log("[结束] 友情召唤引擎已退出")

    def _set_friend_state(self, text: str, color: str) -> None:
        self.friend_state_label.setText(text)
        self.friend_state_label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {color};"
        )

    def refresh_friend_windows(self) -> None:
        cur = self.friend_combo.currentData()
        self.friend_combo.clear()
        for hwnd, title in list_windows():
            self.friend_combo.addItem(title, hwnd)
        if cur is not None:
            idx = self.friend_combo.findData(cur)
            if idx >= 0:
                self.friend_combo.setCurrentIndex(idx)

    # ================= 模板录制 =================
    def current_hwnd(self) -> int | None:
        return self.win_combo.currentData()

    def _pick_region(self) -> tuple | None:
        """弹出框选（覆盖所有显示器），返回物理像素矩形 (x1,y1,x2,y2)；取消返回 None。"""
        return RegionSelector.select_region()

    def _capture_region(self, rect: tuple, hwnd: int | None = None):
        if hwnd is None:
            hwnd = self.current_hwnd()
        if hwnd is None:
            QMessageBox.warning(self, "提示", "请先在英雄卡选择模拟器窗口")
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
        rec_hwnd = (
            self.friend_combo.currentData() if key.startswith("friend") else None
        )
        img = self._capture_region(rect, rec_hwnd)
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
        # 友情召唤槽位
        for key, _, _ in FRIEND_SLOTS:
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

    def _set_state(self, text: str, color: str) -> None:
        self.state_label.setText(text)
        self.state_label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {color};"
        )

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
                "请先在「助战第" + str(use_row) + "行」处点「框选」选取整行，"
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
            f"font-size: 12px; font-weight: 700; color: {_T['text']};"
        )

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
        self._set_state("待机", _T["label2"])
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
        if self._friend_engine is not None:
            self._friend_engine.stop()
            self._friend_engine.wait(2000)
        super().closeEvent(event)
