# Windows 原生运行与核心验收

当前门槛：先完成本表，再开发全局快捷键、选词、区域截图 OCR。Windows 状态为**待执行**，不以 WSL、mock 或 offscreen 代替原生可见窗口和真实服务验收。

## 1. 独立环境

安装 Windows 原生 Python 3.13（包含 `py` 启动器），将项目源码放在 Windows 本地目录，例如 `C:\Projects\wordloom`。复制 `src`、`tests`、`checks`、`scripts`、`docs`、`pyproject.toml`、`README.md`；不复制 WSL `.venv`、业务数据库或任何凭据。不要在 WSL 中执行以下命令。

在 Windows PowerShell 中：

```powershell
cd C:\Projects\wordloom
py -3.13 -c "import sys, platform; print(sys.executable, sys.platform, platform.machine())"
py -3.13 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -e .
.\.venv-win\Scripts\python.exe -m pip check
.\.venv-win\Scripts\python.exe -c "from PySide6.QtWidgets import QApplication; print('Qt Widgets OK')"
.\.venv-win\Scripts\python.exe -m wordloom
```

以上是首次安装。以后只运行最后一条命令；不需要激活虚拟环境。已有 `.venv-win` 时不重复创建。等价的便利入口为 `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows.ps1 install`，之后将末尾 `install` 改为 `start` / `validate` / `mock` / `build`。该执行策略选项只作用于本次 PowerShell 进程；也可完全不用脚本，直接执行 Python 命令。脚本仅使用 `.venv-win\Scripts\python.exe`，不会触碰 WSL `.venv`。

## 2. 自动验证

```powershell
.\.venv-win\Scripts\python.exe scripts\validate.py --native-credentials --output validation\windows
```

退出 0 才表示所运行的自动检查通过；1 是失败，2 是环境受限。保存 `validation\windows\results.json` 及同目录日志。验证器固定子进程 UTF-8，中文路径和日志不依赖 Windows 默认代码页。

这包括真实 loopback HTTP、流式中断/取消、Qt 控件操作、跨进程 SQLite 重启持久化；新增联合用例通过界面启动真实本地 HTTP 流，收到文本后取消、确认工作线程退出，再请求并保存复习。自动窗口使用 offscreen，不替代下一节可见窗口验收。

`--native-credentials` 会在系统凭据库写入一个随机测试值，另起 Python 进程读取，然后删除并确认消失；不读取已有模型配置或用户密钥。凭据值不进入命令行参数和日志。若清理失败，日志给出测试项的 service/account，需在系统凭据管理器删除。没有此参数时不会写测试凭据。单独执行：

```powershell
.\.venv-win\Scripts\python.exe scripts\check_credentials.py
```

## 3. 可见窗口与真实服务

先用独立验收目录启动；以下命令始终使用同一目录以验证重启：

```powershell
.\.venv-win\Scripts\python.exe -m wordloom --data-dir "$env:LOCALAPPDATA\WordLoom-Acceptance"
```

| 项目 | 操作和通过条件 | 当前结果 |
|---|---|---|
| 原生窗口 | 窗口可见、中文输入和粘贴正常，系统缩放下按钮可用 | 待验证 |
| 真实 API | 在设置中自行填 Base URL、模型、Key；选系统保存，执行连接测试；翻译一个新句子，关闭流式再测一次。列表不支持时手动模型仍能使用 | 未提供配置，待验证 |
| 流式与取消 | 请求长文本，确认增量出现且窗口可操作；输出期间取消，状态变为已取消，不能收藏不完整结果；紧接着新请求正确完成。也用下节慢速 mock 检查可重复取消 | 待验证 |
| 凭据重启 | 保存配置后完全退出程序，再按同一命令启动，不重输 Key 能请求；切换不同服务地址不会携带旧 Key；清除测试配置凭据后检查系统库 | 待验证 |
| 词库重启 | 翻译后收藏词语、原文上下文和释义；编辑释义；完全退出重开，搜索仍可找到修改后的内容；复制结果到记事本核对 | 待验证 |
| 复习进度 | 显示答案后点“记住”；关闭重开，该词不再在当前到期队列。导出 JSON 核对 repetitions=1、interval=1、due 为约一天后；JSON 导入另一测试词库仍保留进度 | 待验证 |
| 错误恢复 | 错误 Key 显示鉴权失败、429 显示限流；取消/超时后无无限重试；修正配置重新请求成功 | 待验证 |
| 明文隔离 | 设置/数据库/导出不含测试密钥；仅检查自建测试数据，不提交真实密钥或业务文本 | 待验证 |

真实服务由用户在本机界面配置，不把 API Key 放入命令行、环境文件或反馈日志。连接测试和验收请求可能产生服务商用量。当前传输直连，不读取系统/环境代理；需要代理的部署尚未支持。仅能证明本次所选服务/模型兼容，不能据此宣称所有 OpenAI 兼容地址均通过。配置与 Key 不属于词库导出内容。

## 4. 可重复的本地故障验收

另一个 PowerShell 窗口运行：

```powershell
cd C:\Projects\wordloom
.\.venv-win\Scripts\python.exe scripts\mock_server.py --port 8765
```

应用新建无 Key 配置，根地址 `http://127.0.0.1:8765/v1`。`mock-stream` 检查增量；`mock-slow-stream` 检查收到内容后取消；`mock-json` 检查非流式；`mock-auth` / `mock-rate` / `mock-invalid` / `mock-interrupted` 检查鉴权、限流、异常响应、中断。超时用 `mock-timeout` 并将配置超时设为 1 秒。退出此服务用 Ctrl+C。输出标有 MOCK，不算真实翻译验收。

## 5. 反馈与进入下一阶段的条件

记录 Windows 版本/架构、原生 Python 路径、自动日志、上述每行通过/失败/未测及复现步骤。实际模型测试记录协议、模型名称、流式能力、错误分类即可，不记录 Key、请求头或私有地址。失败保留实际错误；未执行不能打勾。修复后复跑相关检查。

只有自动检查无失败/跳过、可见窗口核心流程及用户真实服务通过后，才进入 Windows 快捷键、选词与截图 OCR；打包/签名属于独立验收，不由源码运行推导成功。

macOS：共用 UI/业务/请求代码、Keychain 适配和构建脚本已存在；原生窗口、Keychain、网络、签名公证和系统集成均未验证。本轮没有增加 macOS 系统功能，不使用 Windows 结果替代它，继续记录在 [双平台清单](NATIVE_CHECKLIST.md)。
