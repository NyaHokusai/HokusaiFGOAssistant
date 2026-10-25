<div align="center">

<img src="assets/icon.png" width="128" alt="HFA - 葛饰北斋"/>

# 北斋FGO助手 · HokusaiFGOAssistant (HFA)

![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Version](https://img.shields.io/badge/version-1.0.1-6C63FF)
![License](https://img.shields.io/badge/license-MIT-orange)

纯本地运行的 FGO（Fate/Grand Order）辅助工具：**战斗本体由玩家手动打**，
每局结束后程序自动接管结算流程并进入下一把。纯屏幕截图 + 模拟点击，
不读取内存、不修改游戏数据、不发包。

</div>

---

## 特性

- 内置识别模板，开箱即用，无需逐个录制
- 「持续 n 秒」防抖机制，结算动画再花也不会误触
- 助战 1/2/3 行分别录入，软件内一键切换（运行中也可换）
- 没体力自动吃黄金果实补体力
- 窗口/阈值/助战行等设置自动记忆
- 多显示器 + DPI 缩放适配，副屏框选也精准

## 自动化流程（每局结束后循环）

```
战斗结束 → 识别「战斗结果」标题持续 n 秒 → 点击屏幕正中央（结算第1、2页各点一次）
        → 识别「请点击游戏界面」持续 n 秒 → 点击屏幕正中央
        → 识别「下一步」持续 n 秒 → 点击识别位置（出现几次点几次）
        → 识别「连续出击」持续 n 秒 → 点击识别位置
        → [没体力时] 弹出行动力回复 → 点击「黄金果实」→ 点击「决定」
        → 识别「助战选择」→ 点击玩家录入的助战位置
        → 下一把战斗开始（玩家手动打）
```

- **持续 n 秒**：识别到目标需在画面上连续稳定显示 n 秒才点击（软件内可调，默认 1 秒），
  避免结算动画过程中误触。
- **内置模板**：战斗结果 / 下一步 / 连续出击 / 助战选择 四个文字模板已随软件内置，
  开箱即用；如识别不理想可在界面上框选覆盖为自定义模板（自定义优先于内置）。

## 运行环境

- Windows 10/11，Python 3.10+
- FGO 运行在安卓模拟器（MuMu / 雷电 / LDPlayer 等），横屏

## 安装与启动

```powershell
cd fgo-assistant
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## 使用步骤

> 多显示器说明：每块显示器都会出现框选遮罩，任意屏幕均可框选；框选输出
> 物理像素坐标，125%/150% 缩放、副屏、混合 DPI 下都准确。

1. 启动模拟器并进入 FGO。
2. 在顶部「目标窗口」选择模拟器窗口（找不到点「刷新」；直接点开始也会弹窗让你选）。
3. **录入助战位置**（唯一必须手动做的）：在「助战第1/2/3行」处分别点「框选」
   选取整行（可只录一行，也可以三行都录）；用上方的「使用: 第1/2/3行」单选
   切换要点哪一行，**运行中也能随时切换**。
   其余模板已内置；黄金果实/决定两个可选模板如需自动补体力，再手动框选。
4. 点 **▶ 开始**。程序开始监控画面，你手动打完这一把即可，结算流程全部自动。
5. 点 **■ 结束** 停止；紧急情况下把鼠标快速甩到**屏幕左上角**（FAILSAFE）。

> 窗口、阈值、持续秒数、助战行选择会自动保存在 `config.json`，下次打开自动恢复。

## 调参

- **识别阈值**：默认 0.80。把别的界面误认成按钮 → 调高；该点的时候没点 → 调低。
- 运行日志会打印每次命中的模板和匹配得分，方便定位问题。
- 换模拟器分辨率后需要重新录制所有模板。

## 打包成 EXE

项目根目录的 `build_exe.ps1` 是一键打包脚本（PyInstaller）：

```powershell
powershell -ExecutionPolicy Bypass -File build_exe.ps1
```

产物在 `dist\HFA.exe`（单文件，约 100MB，双击即可运行，无需装 Python）。

**打包后还能改吗？**

- **模板图 / meta.json 可以直接改**：exe 运行时会在自己旁边创建
  `assets\templates\`，里面的 png 模板可以直接替换、删除，meta.json 可以编辑，
  不需要重新打包。
- **改程序逻辑需要重新打包**：修改源码后重跑一次 `build_exe.ps1` 即可，几十秒出新包。
- 想改成「文件夹版」（启动更快、体积分散）：把脚本里的 `--onefile` 改成 `--onedir`。

## 目录结构

```
fgo-assistant/
├── main.py                  # 入口（含 DPI 感知）
├── requirements.txt
├── app/
│   ├── capture.py           # 窗口枚举 + mss 截图
│   ├── region_selector.py   # 全屏半透明框选
│   ├── recognizer.py        # OpenCV 模板匹配
│   ├── actor.py             # pyautogui 点击
│   ├── fgo_engine.py        # 结算流程状态监控引擎
│   └── main_window.py       # 主界面
└── assets/templates/        # 录制的模板图 + meta.json（助战点击位置）
```

## 免责声明

本工具仅供学习交流。使用第三方辅助存在违反游戏用户协议、导致账号被封的风险，
请自行斟酌，后果自负。
