# 语笺 WordLoom

独立编写的 Python / PySide6 桌面词库：**自定义模型翻译 → 收藏原文与上下文 → 离线复习**。使用自己的名称、界面和代码；不加载分析样本，不读取其他软件的凭据，不连接原软件服务。

用户已报告 Windows 原生可启动、核心功能正常。本轮修复深色模式，新增“外观与快捷键”设置及 Windows 全局唤起/隐藏快捷键（默认 Ctrl+Alt+W）。自动测试通过的范围与 Windows 原生待验收项见 [M2.1 说明](docs/M2_WINDOWS_HOTKEY.md)。按顺序先验收这一项，再做选词、区域截图 OCR、托盘；macOS 原生状态单独记录。

## 启动（已安装依赖的当前 WSL 环境）

在普通 WSL 终端执行；使用现有项目虚拟环境，无须重复安装：

```sh
cd /home/xlawy/Workspace/Personal-Project/reverse-cishi/reverse/cishi/wordloom
.venv/bin/python -m wordloom
```

独立测试数据目录：

```sh
.venv/bin/python -m wordloom --data-dir /tmp/wordloom-manual-check
```

导入 `PySide6` 成功不一定表示图形库完整，可以先检查：

```sh
.venv/bin/python -c 'from PySide6.QtWidgets import QApplication; print("Qt Widgets import OK")'
```

早期沙箱曾报告 `libEGL.so.1` 缺失，本轮已可导入 QtWidgets 并通过 offscreen 启动。如果其他环境出现同样错误，需在系统侧补齐 EGL 运行库（Debian/Ubuntu 对应 `libegl1`），不是重新安装 Python 包。普通窗口还需 WSLg/X11/Wayland 显示环境；`QT_QPA_PLATFORM=offscreen` 只用于自动化控件测试，不代表窗口显示已验证。

## 新系统安装

macOS / 具备 Linux 图形环境的开发终端：

```sh
cd wordloom
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m wordloom
```

Windows PowerShell：

```powershell
cd wordloom
py -3.13 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -e .
.\.venv-win\Scripts\python.exe -m wordloom
```

上述新环境安装命令是交付说明；本轮继续使用用户已安装的 `.venv`，没有重复执行安装。

## 使用

1. 打开“模型与 API 设置”，新建文本翻译配置，填服务商的完整 API 根路径（如 `https://服务商/v1`），选择 OpenAI 兼容 Chat Completions 协议。
2. 手动填模型 ID；服务支持 `GET /models` 时可获取列表。模型列表不代表图像能力，也不保证该模型接受温度等参数。
3. 填 API Key。Windows/macOS 通过原生系统凭据库保存；WSL/Linux 开发环境只提供显式会话模式。空 Key 也可用于无鉴权的本地服务。Key 留空表示保留当前地址的已有凭据，清除需显式勾选。临时会话 Key 退出后消失；它不会覆盖此前保存在系统库的 Key。
4. 调整超时、流式、温度、输出长度及长度字段；不支持某参数时可以不发送。修改翻译、释义、例句各自的 system 提示词，然后测试并保存。连接测试也会调用模型，可能计入服务商用量。
5. 输入/粘贴原文与上下文，选择翻译/释义/例句。请求期间可取消；失败显示类型并允许手动重试。服务响应按纯文本展示，模型文本不执行 HTML/脚本。
6. 检查结果，复制或保存到词库。可将原文中的一个词作为标题，完整原文并入上下文。失败或取消的部分输出不允许保存为完整结果。
7. 词库支持原文/上下文/释义搜索、编辑、删除及 JSON/CSV 导入导出。JSON 保留当前排期；CSV 仅交换词条，导入时重新排期。重复原文+上下文跳过，不覆盖已有进度。导出的是全部词库，不仅当前搜索结果；不包含模型配置和 Key。
8. 复习页先回想，再显示答案并评分。没记住 10 分钟后重现；首次记住 1 天，后续约 ×2.2；有点难约 ×1.2。评分即时持久化。这是首版自有简单间隔算法，不是 FSRS。

## 当前边界

- 支持 OpenAI-compatible Chat Completions 的 SSE 和 JSON 响应；不自动把任意服务地址当成兼容端点。后续可增加 `providers.Adapter` 实现。
- 默认不自动重试、不跟随重定向，不忽略 TLS 验证。仅本机回环地址允许 HTTP。当前 HTTP 实现直连服务，不自动使用系统/环境代理；依赖代理的服务需要后续代理适配。
- 翻译与 OCR 配置独立；OCR 只有显式图像能力开启后才构造图片请求，目前可做图像连接测试。用户选图、区域截图和取词联动属于 M2。
- Windows 全局唤起/隐藏快捷键代码已实现，原生验收待完成；选区、托盘、发音、账户同步、自动更新未实现。macOS 全局快捷键明确不可用。详见 [功能对照表](docs/FEATURE_MATRIX.md)。
- 改变 API 地址会改变凭据标识，旧 Key 不会发送到新地址。旧地址的凭据可能仍留在系统库；可恢复旧地址后勾选清除，或在系统凭据管理器中删除 `org.wordloom.desktop.api` 对应项。删除配置清理其当前地址的凭据。

## 数据

默认位置：Windows `%LOCALAPPDATA%\WordLoom`；macOS `~/Library/Application Support/WordLoom`；Linux `~/.local/share/wordloom`。可用 `--data-dir` 或 `WORDLOOM_DATA_DIR` 指定。

`settings.json` 仅保存非秘密配置；`library.sqlite3` 保存词条、当前排期、评分历史。只有用户点击请求时才发送相应输入到用户配置的模型服务。当前没有同步或后台请求；JSON 备份保留当前复习状态，不含逐次评分历史。备份整个数据库时先退出应用。

## 测试与模拟服务

```sh
.venv/bin/python scripts/validate.py
```

结果写入 `validation/`。返回 0：所运行的检查通过；1：应用/测试失败；2：有环境受限的检查。环境受限不会被记为通过。`tests/` 包括真实 QtCore 事件循环与独立的本地 HTTP 测试；`checks/test_ui.py` 在单独进程中运行控件验收，避免 QCoreApplication/QApplication 混用。

普通终端可手工运行无密钥的模拟服务：

```sh
.venv/bin/python scripts/mock_server.py --port 8765
```

在应用中设置 Base URL `http://127.0.0.1:8765/v1`，模型 `mock-stream` 或 `mock-json`。输出明确标注 `[MOCK]`，仅用于验收请求链路，不是真实翻译。`mock-auth`、`mock-rate`、`mock-timeout`、`mock-invalid`、`mock-interrupted`、`mock-slow-stream` 分别检查错误、超时、中断和取消。模拟服务只在脚本中，生产应用没有固定结果回退。

## 文档

- [GitHub 与 Windows/Linux 源码同步](docs/GIT_SYNC.md)
- [技术方案与里程碑](docs/PLAN.md)
- [证据、拟实现行为与状态对照](docs/FEATURE_MATRIX.md)
- [实际验证记录](docs/VALIDATION.md)
- [Windows/macOS 构建与原生验收](docs/NATIVE_CHECKLIST.md)

下一步在 Windows 验收本次主题修复与全局快捷键。详见 [M2.1 操作与记录表](docs/M2_WINDOWS_HOTKEY.md)，通过后继续选词翻译。
