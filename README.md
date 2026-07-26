# 系统优化工具箱

![图标](icon.png)

Windows 系统优化工具箱（tkinter GUI，单文件 `.pyw`），自带多分辨率 `.ico` 图标。

## 设计

**深色玻璃拟态现代 UI**（`tkinter` + 全自绘 + 全局深色 ttk 主题，纯零额外依赖）：

- **无边框窗口**（`overrideredirect` + Win11 DWM 圆角 + 拖拽），1180×760
- **自绘渐变标题栏**（靛蓝 #6366f1 → 青 #22d3ee 水平渐变），含 macOS 风格三圆点（红=关 / 黄=最小化）
- **左侧竖向导航栏**（224px，4 个视图：首页 🏠 / 清理 🧹 / 优化 ⚡ / 工具 🧰），选中态有左侧 3px 靛蓝指示条 + 背景高亮，hover 微亮
- **4 个卡片化视图**（`tkraise` 切换）：
  - **首页**：渐变英雄区（"让系统重新呼吸" + 双 CTA 按钮）+ 3 个统计装饰卡（可清理 / 优化 / 工具数量）+ 高危红字提示
  - **清理**：顶部工具栏 6 个自绘圆角按钮（扫描/清理/导出/全选/全不选/仅低风险），深色 Treeview（30 项可清理 + 高危行红色 + 选中行柔和深绿），底部统计文字
  - **优化**：15 项一键优化，3 列 × 5 行卡片网格，每卡图标标题 + 描述 + 靛蓝"执行"按钮
  - **工具**：可滚动 canvas，三段分组（Windows 系统工具 9 / 优化与卸载面板 6 / 外部工具 2），卡片带靛蓝"打开"按钮
- **自绘控件**：
  - `GradButton(tk.Canvas)`：真圆角矩形 + 顶部高光 + 实心渐变（主）/ 描边（次）两态，hover 提亮 16%，`surround=` 父背景色消除圆角外方块
  - `RoundedCard(tk.Canvas)`：真圆角卡片容器（背景透明，圆角外即透明），内容用 `create_text` + `create_window` 叠放
  - 背景 canvas：垂直深色渐变（#0d1117→#0a0d12）+ 右上青色光晕 + 左下紫色光晕
- **底部运行日志**：固定深色 ScrolledText，跨视图常驻
- **全局深色 ttk 主题**（clam）：Treeview、按钮、滚动条全统一深色，弹出的子窗口（卸载预装/深度优化/GPU/电源/启动项/Duck）也自动跟随

所有后端逻辑（注册表/服务/计划任务/清理/优化/扫描/导出/启动项枚举/UAC 提权/统计）完全保留，仅重写 UI 外壳。

## 功能

- **安全清理**：缓存 / 垃圾文件定向清理。UAC 标准提权，删除前先扫描预览、手动勾选、二次确认；只清系统 / 应用临时与缓存，不碰个人目录（文档、图片、下载、桌面等）。
- **一键优化**：高性能电源、卓越电源、快速启动、关闭防火墙、关闭 Windows Defender、关闭 UAC、关闭系统还原、关闭 Win 更新、清理 DNS、关闭传递优化（DoSvc）、禁用 SysMain、关闭搜索索引、关闭透明动画、关闭遥测、关闭休眠。每项执行前二次确认，并注明可逆恢复方法。
- **卸载预装应用**：内置 36 项 Win10/11 预装 UWP 应用清单（计算器、照片、Xbox、Groove、天气、Spotify 等），一键“检测已安装”并批量卸载。仅卸当前用户、卸载后可从 Microsoft Store 重装（可逆），系统 UI 组件（如 XboxGameCallableUI）自动排除。清单与卸载思路整合自开源项目 [PyDebloatX](https://github.com/Teraskull/PyDebloatX)（MIT License）。
- **深度优化**：整合自开源 [Optimizer](https://github.com/hellzerg/Optimizer)（MIT License）的 19 项注册表 / 服务微调开关面板，可勾选、一键“应用所选”或“还原所选”（全部可逆）。覆盖 Xbox 游戏栏 / 录制、Widgets、Teams Chat、Copilot、开始菜单广告、资讯与兴趣、粘滞键、长路径、云剪贴板、Edge 遥测、错误报告（WER）、定位传感器、快速访问、拼写预测、Windows Ink、Snap 助手、Win11 经典右键菜单、性能微调、SmartScreen（高风险，谨慎开启）。与“一键优化”区刻意不重复（遥测 / SysMain / 系统还原 / 搜索索引 / 透明 / Win 更新 / 传递优化 / UAC / Defender / 防火墙 / 休眠等不在本面板）。
- **GPU 优化**：整合自开源 [optimizerDuck](https://github.com/itsfatduck/optimizerDuck)（GPL v3）的显卡深度调优。运行时读取注册表自动检测本机显卡厂商，仅显示 AMD / NVIDIA / Intel 适用的 8 项开关（禁用 ULPS、电源门控、时钟门控、ASPM、动态 / 异步 P-state、异步翻转、自适应垂直同步），写入 `HKLM\...\Control\Class\{4d36e968-...}\XXXX`，全部可逆（还原即删除覆写值恢复驱动默认）。
- **电源 / 性能细项**：整合自 optimizerDuck 的两项独有调整——禁用系统电源节流（PowerThrottlingOff=1 + 关闭 USB 意外移除自动恢复）、禁用 USB 设备节能挂起（CIM `MSPower_DeviceEnable`），降低延迟、提升性能。
- **启动项管理**：整合自 optimizerDuck 的启动项管理器。枚举本机开机自启项（注册表 Run 键 / 启动文件夹 / 计划任务），勾选后一键“禁用所选 / 启用所选”，通过 `StartupApproved` 注册表标志或计划任务状态切换，可逆。
- **optimizerDuck 全功能优化**：整合自 optimizerDuck 其余独有优化类别（Performance / UserExperience / SecurityAndPrivacy / PowerManagement）的去重后 16 项开关面板，可勾选、一键“应用所选 / 还原所选”（全部可逆）。覆盖：禁用后台应用、SvcHost 拆分阈值（按本机内存）、前台进程优先、MMCSS 多媒体调度（游戏/低延迟）、键盘延迟优化、加速资源管理器与菜单、关闭视觉特效、禁用开始菜单网页搜索、关闭遥测与诊断（注册表 + 禁用 DiagTrack 等 5 项服务 + 10 个诊断计划任务）、关闭广告与建议、关闭活动历史、关闭 WMI AutoLogger、禁用 Cortana 与网页搜索、关闭内容分发管理器、关闭休眠与快速启动、切换高性能电源计划。
- **运行日志面板**：底部实时显示操作结果（跨视图常驻，3 行紧凑）。
- **自定义应用图标**：窗口左上角、任务栏、Alt-Tab 均显示 `icon.ico`（多分辨率：16/24/32/48/64/128/256）。

## 使用

1. 确保已安装 Python 3 且带 `tkinter`（Windows 自带）。
2. 双击 `系统优化工具箱.pyw` 运行。
3. 涉及系统设置的操作，在当前非管理员时会弹出 UAC 提权确认；执行前均二次确认，全部可逆。

> 首次运行需保证 `icon.ico` 与 `.pyw` 在同一目录，否则会回退到 tkinter 默认图标。

## 外部工具路径配置

文件顶部常量中已配置外部工具位置，请按你电脑的实际路径修改：

- `WIN10_OPTIMIZER_BAT = r"D:\系统优化\win10_优化版.bat"`
- `NET_ASSIST_EXE = r"C:\Users\Administrator\Desktop\360联网助手.exe"`

找不到对应文件时工具会弹窗提示，不会崩溃。

## 打包为单文件 exe

使用 PyInstaller 一键打包（包含图标 + 两个外部文件）：

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --icon icon.ico \
  --name "系统优化工具箱" \
  --add-data "D:/系统优化/win10_优化版.bat;win10_优化版.bat" \
  --add-data "C:/Users/Administrator/Desktop/360联网助手.exe;360联网助手.exe" \
  --add-data "icon.ico;icon.ico" \
  --add-data "icon.png;icon.png" \
  系统优化工具箱.pyw
```

产出 `dist/系统优化工具箱.exe`（约 15MB），双击即可运行，无需任何依赖。

> 提示：单文件 exe 会把 `360联网助手.exe` 解压到 `%TEMP%\_MEIPASS` 再执行，少数杀毒软件可能误报，自用可加白名单。

## 文件说明

- `系统优化工具箱.pyw` — 主程序
- `icon.ico` — Windows 多分辨率图标（用于打包 exe / 资源管理器 / 任务栏 / Alt-Tab）
- `icon.png` — 图标 PNG 预览（用于 README / 网页显示）

## 安全说明

- 清理项只针对临时与缓存文件，绝不触碰个人数据；删除遇占用 / 权限错误自动跳过。
- 高危操作（关防火墙 / Defender / UAC / 系统还原 / Win 更新）已注明恢复方法，建议按需临时使用，长期关闭会降低系统安全性。
- 卸载预装应用仅作用于当前用户，卸载后可从 Microsoft Store 重新安装。
- 深度优化面板所有项均可一键还原；其中 SmartScreen 为高风险开关，关闭后会降低浏览器/下载防护，仅建议临时使用。
- 本仓库文件含作者机器的硬编码路径（如 `C:\Users\Administrator`、`D:\系统优化`），他人使用时请改为自己的实际路径。

## 致谢

- 预装应用卸载清单与思路来自 [PyDebloatX](https://github.com/Teraskull/PyDebloatX)（MIT License，Copyright © 2020-2021 Anton Grouchtchak）。
- 深度优化面板的注册表 / 服务调整移植自开源 [Optimizer](https://github.com/hellzerg/Optimizer)（MIT License，Copyright © 2019-2024 hellzerg）。
- GPU 优化、电源 / 性能细项、启动项管理移植自开源 [optimizerDuck](https://github.com/itsfatduck/optimizerDuck)（GPL v3，Copyright © 2026 fatDuck）。

## 免责声明

仅供学习与自用。修改系统设置前请确认已了解后果。
