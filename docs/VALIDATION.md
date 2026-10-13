# 验证记录（2026-10-13 更新）

> 当前状态：用户已确认 Windows 主题与唤起/隐藏快捷键通过；随后反馈选区读取兼容性不足。M2.2 现改为鼠标指向后按快捷键，UIA 指针读取 → 本机 OCR 回退 → 浮窗释义/收藏。Windows 新增原生能力待验收，macOS 尚未实现。详见 [当前实现、边界和验收](M2_POINTER_LOOKUP.md)。下文此前阶段记录中的“待验收/下一步”保留历史含义，以本条和最新验证记录为准。

## 最新：hitbox 阶段后处理调整

用户复测前次修复后仍在 hitbox 阶段失败。改为 Windows 仅枚举导出识别行/词/局部词框，Python 执行坐标转换、校验、命中和上下文处理。错误细分到导出阶段，并显示经过类型及范围限制的脚本行号/HRESULT，不回显异常文本。

`validation/ocr-hitbox/` 实测：69 项核心通过；真实 HTTP 类在 setUpClass 因 socket 环境限制跳过。界面 17 项中 16 通过、1 项真实 HTTP/UI 跳过，离屏启动通过，整体返回 2。新增原始 OCR→回退调度→词框/上下文测试，以及异常数据、空/未命中、单行、负坐标、上下文截断与诊断字段隐私检查通过。diff 检查通过。

Windows PowerShell 导出器回归脚本已更新，但本机实际执行仍报 `UtilBindVsockAnyPort:317: socket failed 1`，退出 1；未运行原生脚本回归或微信/WPS 复测。具体异常根因尚不能由上一版 hitbox 标签唯一确定，不将改造写成原生验收已通过。macOS 状态不变。

## 最新：OCR 词框修复

用户已反馈 Notion/Chrome/终端可用，微信/WPS 返回泛化 OCR 错误。已修正 PowerShell 坐标数组内加法的优先级错误，新增安全的阶段标签及无文字/未命中区分；尚无修复后原生复测结论。

`validation/pointer-ocr-fix/`：64 项核心通过，真实 HTTP 类在 setUpClass 环境跳过；17 项界面中 16 通过、1 项 socket 联合检查跳过；启动通过。验证器返回 2（环境受限）。新增错误协议测试确认只显示固定阶段标签，不回显未知字段。`git diff --check` 通过。

新增 `scripts/check_pointer_worker.ps1` 从生产脚本提取函数，检查语法、坐标转换及命中；实际启动 Windows PowerShell 仍报 `UtilBindVsockAnyPort:317: socket failed 1`，退出 1，因此原生回归未运行，不能以 Python 测试代替。复测步骤见 M2_POINTER_LOOKUP.md。

## 最新：指针取词与浮窗修正

用户选择“鼠标指向后按快捷键取词”。默认 Ctrl+Alt+T 已改为该模式；旧选区模式可选。Windows UIA 指针接口、本机局部 OCR 与浮窗实现见 [M2_POINTER_LOOKUP.md](M2_POINTER_LOOKUP.md)。

本轮 `.venv/bin/python scripts/validate.py --output validation/pointer` 实际结果：

- 核心运行 63 项通过；真实 HTTP 测试类在 setUpClass 因 `Operation not permitted` 跳过，不计作通过。
- 界面共 17 项：16 项通过、1 项真实 HTTP/UI 联合用例因 socket 权限跳过。
- offscreen 启动通过；compileall、git diff --check 通过。浮窗明暗主题截图已在 `validation/pointer/popup-dark.png`、`popup-light.png` 检查，属于 WSL 离屏视觉检查。
- 新增测试涵盖真实子进程管道复用、超时终止、取消、请求 ID 拒绝旧结果；模拟 UIA/OCR 回退及错误；偏好迁移和持久化；实际 Qt 浮窗→内存 HTTP 模型响应→保存上下文/释义→复习；修改失效、Esc 取消、手动粘贴入口和负坐标布局。
- 真实 Windows UIA/OCR 返回值在共用测试中由替身提供，不代表 Windows 原生识别、焦点或多屏缩放通过。再次尝试 Windows PowerShell 互操作，实际仍报 `UtilBindVsockAnyPort:317: socket failed 1`，退出 1。

验证器整体返回 2（环境受限），未把跳过项目记为通过。日志保存在本机 `validation/pointer/`（Git 忽略）；Windows 原生、真实模型和 macOS 新增系统能力未验证。无需新增 Python 包。

## 最新：选词翻译

用户已反馈 M2.1 原生验收通过。本轮 M2.2 代码与共用测试完成：55 项核心、12 项界面测试和 offscreen 启动通过，真实 HTTP 组及 1 项 HTTP/UI 联合检查环境跳过。Windows UI Automation 未在 agent 实测；[详细实现、测试边界与验收表](M2_SELECTION.md)。以下为此前阶段记录。

## 最新：主题修复与 M2.1

用户报告 Windows 原生启动和现有功能正常。本轮主题/快捷键代码及原生验收门槛见 [M2_WINDOWS_HOTKEY.md](M2_WINDOWS_HOTKEY.md)。本轮 47 项核心测试通过、8 项 UI 测试通过、1 项 UI/HTTP 联合测试环境跳过，offscreen 启动通过；核心 HTTP 类仍因套接字跳过。下文是此前阶段记录，不代表新增功能已在 Windows 实测。

## 证据分开保留

普通 WSL 终端的新日志已经出现在项目 `validation/` 中，本轮读取后原样归档到 [ordinary-wsl-20261013](../validation/ordinary-wsl-20261013/results.json)，没有用 agent 的受限结果覆盖它。日志报告 Python 3.13.5、PySide6 6.12.0、keyring 25.7.0。没有发现这些日志中的应用失败，不虚构“已修复的运行故障”。

| 环境与证据 | 实际结果 | 不能由此推导 |
|---|---|---|
| 普通 WSL，原有 [核心/HTTP 日志](../validation/ordinary-wsl-20261013/core-and-http.log) | 49 项通过，包括 6 项真实 loopback HTTP 请求/模型列表/401/429/超时/取消/中断用例，无 skip | 真实模型服务、Windows 网络未验收 |
| 普通 WSL，原有 [界面日志](../validation/ordinary-wsl-20261013/ui.log) | 6 项控件测试通过，原有 UI 请求使用内存 HTTP 替身 | 不是 UI 与真实 HTTP 联合验收，也不是原生可见窗口验收 |
| 普通 WSL，原有启动 | offscreen smoke-test 退出 0 | 不证明屏幕显示、输入法或 DPI |
| 本轮 agent，[核心/HTTP 日志](../validation/agent-stage2/core-and-http.log) | 44 项执行通过，HTTP 组因 socket 权限跳过；新增跨进程重启测试通过 | HTTP 类 setUpClass skip 不计作 6 个通过 |
| 本轮 agent，[界面日志](../validation/agent-stage2/ui.log) | 7 项中 6 项通过、1 项跳过；新增剪贴板检查通过 | 新增真实 HTTP+GUI 联合用例因 socket 权限未运行 |
| 本轮 agent，[启动日志](../validation/agent-stage2/startup.log) | offscreen 启动退出 0，libEGL 问题本轮已不复现 | 不代表普通窗口或 Windows 通过 |
| Windows 互操作探测 | PowerShell 启动返回 1：`WSL ERROR: UtilBindVsockAnyPort:317: socket failed 1` | 未实际运行 Windows Python、PowerShell 脚本或凭据探针 |
| 真实模型服务 | 用户尚未提供本机配置，未请求 | mock 成功不等于真实翻译验证 |

本轮验证器整体返回 **2（环境受限）**。实际 socket 错误为 `PermissionError: [Errno 1] Operation not permitted`，不认定应用错误。原有普通终端结果和本轮新增测试覆盖不同版本，不将它们拼成“新增测试全部通过”。

## 本轮改动与覆盖

- `scripts/validate.py`：子进程明确 UTF-8、保存执行时间，避免 Windows 本地代码页导致中文输出解码异常；支持显式 `--native-credentials`。
- 测试读取 UTF-8 文件时显式指定编码；不依赖宿主默认编码。
- `tests/test_restart.py`：独立写入进程提交中文词条、评分后退出，父进程重新打开数据库核对释义/上下文/到期/次数/评分历史/当前队列。已执行通过。
- `checks/test_ui.py`：已有复制测试现在实际点击按钮核对剪贴板；新增真实 loopback 的流式取消、工作线程退出、再次请求、保存与复习联合用例。复制检查通过，联合用例待普通终端。
- `scripts/check_credentials.py`：显式写入一次性随机系统凭据、另起进程验证读取、删除并检查；不加载真实配置，不输出密钥。Windows/macOS 尚未执行，不能以假后端单测替代。
- `scripts/windows.ps1`：原生 Python 3.13 创建 `.venv-win`，提供安装、启动、验证、mock 与开发构建入口，未在 Windows 执行。

## 下一次复现

普通 WSL 终端直接复用现有环境，不重新安装：

```sh
.venv/bin/python scripts/validate.py --output validation/ordinary-wsl-stage2
```

预期完整执行 50 项核心/HTTP 和 7 项 UI 测试，再执行启动检查；这是待执行的用例数量，不是已经通过的结果。

Windows 在本地源码目录，使用独立原生虚拟环境：

```powershell
.\.venv-win\Scripts\python.exe scripts\validate.py --native-credentials --output validation\windows
```

安装/启动/真实服务/凭据重启/词库复习重启的详细步骤和待填表在 [WINDOWS_ACCEPTANCE.md](WINDOWS_ACCEPTANCE.md)。结果目录按环境分开。0 表示所有运行检查通过；1 表示失败；2 表示环境受限，不能拿 skip 当验收。

## 平台状态与门槛

| 平台 | 已有证据 | 待验收 |
|---|---|---|
| WSL | 原有实际 HTTP 和控件/启动通过；新增跨进程持久化及复制通过 | 新增 HTTP+GUI 联合用例、真实模型服务、可见窗口 |
| Windows | 共用代码、WinVault 适配、独立环境入口和原生探针已准备 | 原生 Python 安装/运行、凭据跨进程、真实 API、可见窗口闭环、构建全部未验证 |
| macOS | 共用代码、Keychain 适配、构建说明；本轮无新增系统功能 | 所有原生执行/权限/签名公证仍未验证 |

未生成或验证安装包。先完成 Windows 核心验收，修复实际暴露的问题；通过后才实施 Windows 快捷键、选词和截图 OCR。macOS 单独推进，不推定功能对齐。第一阶段输入样本未参与本轮执行，也没有修改 input/。
