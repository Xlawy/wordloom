# 深色模式修复与 M2.1：Windows 全局快捷键

## 本轮范围与状态

用户已报告 Windows 原生可启动、现有功能正常；本轮依据该反馈修复深色模式并实现第一项快捷键。没有把用户报告细化为未提供的凭据/API 测试日志，也不声称新增快捷键已由用户验收。

Windows 快捷键代码已完成，并通过共用逻辑与 Qt 事件分发替身测试。**真实按键触发、前台激活、冲突和退出释放尚待 Windows 原生验收。** 按“每项完成并验证后继续”的顺序，当前停在该验收点，不开始选词、区域截图 OCR 或托盘。当前关闭窗口仍退出程序；快捷键隐藏窗口不退出，可再次唤起。

## 配色修复

旧 QSS 固定浅色文字/输入框，其他容器却继承系统深色调色板。现在由 `theme.py` 同时设置完整 QPalette 和按调色板取色的样式，覆盖窗口、滚动内容、输入框、下拉弹出列表、标签页、表头、选中与禁用状态。数字框上下箭头是本项目自己的 SVG，并纳入源码包及 PyInstaller 数据收集。

“外观与快捷键”提供跟随系统/浅色/深色；默认跟随系统，并在系统切换后重新应用调色板。偏好写入同一数据目录的 `desktop.json`，不改变模型配置、凭据或词库。

已检查 offscreen 深浅截图，输入框、标签和数字框箭头可见：

- [深色 API 设置](../validation/theme-hotkey/api-dark.png)
- [浅色 API 设置](../validation/theme-hotkey/api-light.png)

这是 Linux Qt 渲染证据，不是 Windows 截图。Qt 色彩通知的时序依据 [QStyleHints 文档](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QStyleHints.html)，延迟到系统调色板更新后应用自身颜色。

## 快捷键行为

默认 `Ctrl+Alt+W`，可修改或禁用。主窗口在前台时隐藏；后台、隐藏、最小化时唤起到翻译页。存在设置等模态对话框时先保留并激活该对话框，不把未保存表单藏起来。支持 Ctrl/Alt/Shift/Win 与 A–Z、0–9、F1–F24；至少有 Ctrl/Alt/Win，F12 保留不可用，Windows 保留组合可能注册失败。

Windows 适配层使用 [RegisterHotKey / WM_HOTKEY](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-registerhotkey)，加 MOD_NOREPEAT 防止按住连续开关，不安装键盘钩子、不监听其他按键。共用控制器先注册新组合，保存成功再释放原组合；新组合冲突或配置写入失败时原组合保留。启动时冲突会在主窗口状态栏提示，可打开设置改键。正常退出时注销。

macOS/Linux：全局快捷键未实现，设置明确显示不可用；没有用窗口内 QShortcut 伪装全局支持。共用主题、偏好和窗口逻辑可复用；macOS 主题及系统切换也仍未原生实测。

## Windows 更新与验收

退出旧程序，将更新的 `src`、`scripts`、`tests`、`checks`、`pyproject.toml` 同步到 Windows 项目目录。保留已有 Windows `.venv-win` 和用户数据，不复制 WSL `.venv`。本轮无新增 Python 依赖；已有 editable 安装不需重装。若使用旧打包 EXE，必须另行重新构建，源码更新不会改变旧 EXE。

```powershell
cd C:\Projects\wordloom
.\.venv-win\Scripts\python.exe -m wordloom
.\.venv-win\Scripts\python.exe scripts\validate.py --native-hotkeys --output validation\windows-theme-hotkey
```

自动验证的 `--native-hotkeys` 只临时注册 Ctrl+Alt+Shift+F9/F10/F11 中可用的一组，验证另一进程得到冲突、释放后可复用；不会模拟用户按键，不能替代手动触发。测试组仍包括旧核心业务、HTTP 和界面回归。退出 0 才代表自动检查全部通过；1 为失败，2 为环境受限。

| 验收 | 操作和预期 | 状态 |
|---|---|---|
| 深色/浅色 | 系统深色下打开主窗口、API 设置并滚动到底，打开模型下拉框；文字、数字箭头、复选框可辨。显式切换浅色/深色和跟随系统，重启保留 | 待 Windows 验证 |
| 核心回归 | 测试 API、流式翻译、取消、保存词库、复习；新主题不影响输入、复制和错误反馈 | 待本次回归 |
| 真正全局唤起 | 前台为记事本时按 Ctrl+Alt+W，WordLoom 出现、输入框聚焦；再按隐藏；隐藏后再次按恢复 | 待验证 |
| 长按和最小化 | 长按组合只切换一次；最小化后可恢复，最大化隐藏再显示保持状态 | 待验证 |
| 模态窗口 | API 设置打开期间按快捷键，不丢失表单且仍可关闭设置 | 待验证 |
| 改键和重启 | 改为 Ctrl+Alt+E，旧键不触发、新键可用；完全退出重启后仍为新键 | 待验证 |
| 冲突 | 使用另一个独立数据目录启动第二实例，注册相同组合会提示占用；第二实例改用空闲组合可用；原实例绑定仍有效 | 待验证 |
| 禁用和退出 | 禁用后不再响应；启用后恢复。退出后另一实例可注册此前组合，无后台孤儿进程 | 待验证 |

冲突验收第二实例可用：

```powershell
.\.venv-win\Scripts\python.exe -m wordloom --data-dir "$env:TEMP\WordLoom-Hotkey-Second"
```

不将默认同目录的“单实例锁”错误当成快捷键冲突。

## 当前执行证据

[本轮验证 JSON](../validation/theme-hotkey/results.json)：47 项核心测试通过；界面 9 项中 8 项通过，1 项真实 HTTP 联合测试因 socket 权限跳过；offscreen 启动通过。新增覆盖快捷键解析、保留键、冲突/写入失败回滚、禁用释放、设置重启、Qt 消息分发到隐藏/唤起、深浅切换及对比度。Win32 API 使用测试替身，并非原生验收。

本轮再次尝试 Windows PowerShell，仍报 `WSL ERROR: UtilBindVsockAnyPort:317: socket failed 1`，因此没有执行 Windows 原生探针。原生探针和快捷键物理触发不能标为通过。

## 后续顺序

1. 本页 Windows 验收完成并修复发现的问题。
2. 选中文字快捷键翻译：失败明确提示，并保留粘贴入口；单独验收权限/前台/剪贴板恢复。
3. 区域截图 → 独立 OCR 配置 → 可编辑识别文字 → 翻译；单独验收多屏/DPI/取消。
4. 托盘、关闭到托盘偏好与明确退出，单独验收无托盘时的回退和退出释放。

macOS 每项另做适配和原生记录，不推定与 Windows 同步完成。
