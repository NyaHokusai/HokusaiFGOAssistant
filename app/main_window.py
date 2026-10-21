"""FGO 连续出击助手 - 主界面。

界面只有三块：目标窗口选择、识别模板录制、开始/结束控制。
开始后引擎持续监控模拟器画面，自动完成：
点击继续 → 下一步 → 连续出击 →（没体力时吃金苹果补体力）→ 选第一个助战。
战斗本体由玩家手动打，打完引擎自动接管结算流程。
"""
from __future__ import annotations

import json
import os
import sys
import time

import cv2
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
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

CONFIG_PATH = None  # 在 __init__ 里按 BASE_DIR 赋值

# (key, 界面显示说明)；助战行位置单独处理（见 _build_support_section）
TEMPLATE_SLOTS = [
    ("battle_result", "「战斗结果」标题（结算页识别，点屏幕正中央）"),
    ("next", "「下一步」按钮"),
    ("attack", "「连续出击」按钮"),
    ("apple", "行动力回复弹窗 - 黄金果实行"),
    ("confirm", "行动力确认弹窗 - 「决定」按钮"),
    ("support_title", "「助战选择」标题文字"),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("HokusaiFGOAssistant (HFA)")
        icon_png = os.path.normpath(os.path.join(TEMPLATE_DIR, "..", "icon.png"))
        if os.path.exists(icon_png):
            self.setWindowIcon(QIcon(icon_png))
        self.resize(680, 620)

        os.makedirs(TEMPLATE_DIR, exist_ok=True)
        self._engine: FgoEngine | None = None
        self._cfg_path = os.path.join(BASE_DIR, "config.json")
        self._cfg = self._load_config()

        self._build_ui()
        self._apply_config()
        self.refresh_windows()
        self._restore_window_selection()
        self._refresh_template_status()

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

    # ================= UI =================
    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        # --- 目标窗口 ---
        win_row = QHBoxLayout()
        win_row.addWidget(QLabel("目标窗口:"))
        self.win_combo = QComboBox()
        win_row.addWidget(self.win_combo, 1)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_windows)
        win_row.addWidget(refresh_btn)
        layout.addLayout(win_row)

        tip = QLabel(
            "使用方法：只需框选录入要点的助战行 → 点「开始」→ 手动进入战斗。\n"
            "打完后程序自动完成：战斗结果页点屏幕正中(×2) → 下一步 → 连续出击 →\n"
            "（没体力自动吃金苹果）→ 点选中的助战行 → 下一把。\n"
            "模板已内置（可框选覆盖）；窗口/阈值/助战行设置会自动记住。"
        )
        tip.setWordWrap(True)
        layout.addWidget(tip)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # --- 模板录制 ---
        layout.addWidget(QLabel("识别模板（内置模板已可直接用，「框选」可覆盖为自定义）:"))
        self._slot_status: dict[str, QLabel] = {}
        for key, desc in TEMPLATE_SLOTS:
            row = QHBoxLayout()
            name = QLabel(desc)
            row.addWidget(name, 1)
            status = QLabel()
            status.setMinimumWidth(72)
            status.setAlignment(Qt.AlignCenter)
            self._slot_status[key] = status
            row.addWidget(status)
            btn = QPushButton("框选")
            btn.setFixedWidth(60)
            btn.clicked.connect(lambda _, k=key: self.on_record(k))
            row.addWidget(btn)
            layout.addLayout(row)

        # --- 助战行（三行可选，运行中可切换） ---
        layout.addWidget(QLabel("助战点击位置（框选整行，点击其中心；至少录一行）:"))
        use_row = QHBoxLayout()
        use_row.addWidget(QLabel("  使用:"))
        self.row_radios: dict[int, QRadioButton] = {}
        for i in (1, 2, 3):
            rb = QRadioButton(f"第{i}行")
            rb.setChecked(i == 1)
            rb.toggled.connect(self.on_use_row_changed)
            self.row_radios[i] = rb
            use_row.addWidget(rb)
        use_row.addStretch(1)
        layout.addLayout(use_row)
        for i in (1, 2, 3):
            row = QHBoxLayout()
            row.addWidget(QLabel(f"        助战第{i}行"), 1)
            status = QLabel()
            status.setMinimumWidth(72)
            status.setAlignment(Qt.AlignCenter)
            self._slot_status[f"support_row{i}"] = status
            row.addWidget(status)
            btn = QPushButton("框选")
            btn.setFixedWidth(60)
            btn.clicked.connect(lambda _, k=f"support_row{i}": self.on_record(k))
            row.addWidget(btn)
            layout.addLayout(row)

        thr_row = QHBoxLayout()
        thr_row.addWidget(QLabel("识别阈值:"))
        self.threshold_spin = QDoubleSpinBox()
        self.threshold_spin.setRange(0.5, 0.95)
        self.threshold_spin.setSingleStep(0.01)
        self.threshold_spin.setValue(0.80)
        self.threshold_spin.valueChanged.connect(lambda _: self._save_config())
        thr_row.addWidget(self.threshold_spin)
        thr_row.addWidget(QLabel("（误点别的就调高，识别不到就调低）"))
        thr_row.addStretch(1)
        layout.addLayout(thr_row)

        hold_row = QHBoxLayout()
        hold_row.addWidget(QLabel("持续秒数 n:"))
        self.hold_spin = QDoubleSpinBox()
        self.hold_spin.setRange(0.0, 10.0)
        self.hold_spin.setSingleStep(0.1)
        self.hold_spin.setValue(1.0)
        self.hold_spin.valueChanged.connect(lambda _: self._save_config())
        hold_row.addWidget(self.hold_spin)
        hold_row.addWidget(QLabel("（识别到目标需持续显示 n 秒才点击，防结算动画误触）"))
        hold_row.addStretch(1)
        layout.addLayout(hold_row)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        layout.addWidget(line2)

        # --- 开始 / 结束 ---
        run_row = QHBoxLayout()
        self.state_label = QLabel("待机")
        self.run_btn = QPushButton("▶ 开始")
        self.run_btn.setMinimumHeight(34)
        self.run_btn.clicked.connect(self.on_start)
        self.stop_btn = QPushButton("■ 结束")
        self.stop_btn.setMinimumHeight(34)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.on_stop)
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.stop_btn)
        run_row.addStretch(1)
        run_row.addWidget(self.state_label)
        layout.addLayout(run_row)

        # --- 日志 ---
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)

        self.setCentralWidget(central)

    # ================= 模板录制 =================
    def current_hwnd(self) -> int | None:
        return self.win_combo.currentData()

    def _pick_region(self) -> tuple | None:
        """弹出框选（覆盖所有显示器），返回物理像素矩形 (x1,y1,x2,y2)；取消返回 None。"""
        return RegionSelector.select_region()

    def _capture_region(self, rect: tuple):
        hwnd = self.current_hwnd()
        if hwnd is None:
            QMessageBox.warning(self, "提示", "请先在顶部选择模拟器窗口")
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
        rows = self._support_rows()
        for key, _ in TEMPLATE_SLOTS:
            label = self._slot_status[key]
            user = os.path.exists(os.path.join(TEMPLATE_DIR, f"{key}.png"))
            builtin = os.path.exists(os.path.join(TEMPLATE_DIR, "builtin", f"{key}.png"))
            if user:
                label.setText("自定义")
                label.setStyleSheet("color: #2e9e44; font-weight: bold;")
            elif builtin:
                label.setText("内置")
                label.setStyleSheet("color: #2471a3;")
            else:
                label.setText("未录制")
                label.setStyleSheet("color: #c0392b;")
        for i in (1, 2, 3):
            label = self._slot_status[f"support_row{i}"]
            if str(i) in rows:
                label.setText("已录入")
                label.setStyleSheet("color: #2e9e44; font-weight: bold;")
            else:
                label.setText("需录入")
                label.setStyleSheet("color: #c0392b;")

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
        self._engine.state_signal.connect(self.state_label.setText)
        self._engine.finished_ok.connect(self.on_engine_finished)
        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self._engine.start()

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
            self.state_label.setText("停止中…")
            self.log("[用户] 已请求结束，等待引擎退出…")

    def on_engine_finished(self, _ok: bool) -> None:
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._engine = None
        self.state_label.setText("待机")
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
