# Windows/macOS 构建与原生验收

用户已报告 Windows Python 原生启动和原有功能正常；本轮主题修复及全局快捷键新增项见 [M2.1 验收表](M2_WINDOWS_HOTKEY.md)。当前没有已构建或已验证的 Windows EXE / macOS app / 安装包。QtCore 的 WSL 测试不等价于双平台通过。以下各项均须在对应系统实际勾选，记录系统版本、CPU 架构、Python/Qt 版本、提交版本和日志。

Windows 先按 [原生运行与核心验收](WINDOWS_ACCEPTANCE.md) 完成 Python 源码运行；尚未通过前不进入系统功能开发。macOS 保留共用实现和 Keychain 适配，尚无原生执行证据。

## 构建

建议各平台使用 Python 3.13 的原生发行版，新建该平台自己的 `.venv`；不要复制 WSL 虚拟环境。源码对 Python 的约束为 3.11+，本轮执行环境为 3.13.5。

Windows PowerShell（在项目目录）：

```powershell
py -3.13 -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -e ".[build]"
.\.venv-win\Scripts\python.exe scripts\validate.py --native-credentials --output validation\windows
.\.venv-win\Scripts\python.exe scripts\build_desktop.py
```

macOS（项目目录，Apple Silicon 使用 arm64 Python；Intel 使用 x86_64）：

```sh
python3.13 -m venv .venv
.venv/bin/python -m pip install -e '.[build]'
.venv/bin/python scripts/validate.py
.venv/bin/python scripts/build_desktop.py
```

脚本调用 PyInstaller 目录式打包；预期输出为 Windows 的 `dist/WordLoom/WordLoom.exe` 或 macOS 的 `dist/WordLoom.app`。这是未签名开发构建流程，不是已交付的签名安装包。发布前另做 Windows 代码签名与安装器、macOS Developer ID 签名及 notarization；本项目不持有这些证书，不自动签名、上传或更新。

## 两平台分别填写

| 验收 | Windows | macOS | 操作 |
|---|---|---|---|
| 原生窗口/输入法/高 DPI | 待验证 | 待验证 | 从终端及包启动；缩放、中文输入、文本选择、窗口尺寸 |
| 新建/编辑/删除/切换配置 | 待验证 | 待验证 | 两个不同服务地址及独立 OCR 配置；重启确认选择 |
| 系统凭据持久化 | 待验证 | 待验证 | Windows Credential Manager/macOS Keychain；重启可用；无明文降级 |
| 凭据锁定/拒绝 | 待验证 | 待验证 | 拒绝 Keychain/Vault 访问后显示错误；显式会话模式可用 |
| 配置地址更换 | 待验证 | 待验证 | 新地址不会自动带上旧 Key；清除/删除后核对凭据 |
| 模型列表/真实 API | 待验证 | 待验证 | 用户自行配置服务；手输模型；关闭不适用参数；无原软件后端 |
| 流式/取消/超时/重试 | 待验证 | 待验证 | 用本地 mock 各场景，再测真实服务；界面持续响应 |
| 保存/复制/词库编辑 | 待验证 | 待验证 | 长文本及中文；词语与上下文关联；修改和删除 |
| 导入/导出/重启 | 待验证 | 待验证 | JSON 保留进度；CSV 仅词条；非法文件无部分写入 |
| 复习持久化 | 待验证 | 待验证 | 先揭示后评分；重启复核到期、次数；重复评分被拒绝 |
| 退出/第二实例 | 待验证 | 待验证 | 请求过程中退出；同一数据目录第二次打开提示已占用 |
| 打包后离线运行 | 待验证 | 待验证 | 干净系统、不依赖开发环境；离线词库/复习 |

## 后续平台功能

Windows 全局唤起/隐藏快捷键已获用户原生验收通过反馈；Windows 选区读取已实现，待 [M2.2 原生验收](M2_SELECTION.md)。macOS 快捷键与选区、两平台截图、系统 TTS 和托盘尚未实现。M2 在 Windows 验证 UI Automation、热键冲突和多屏 DPI；在 macOS 验证 Accessibility、Screen Recording 权限与授权后恢复。剪贴板复制回退需要验证原内容恢复、前台切换和取消；在此之前不启用自动 Ctrl+C/Cmd+C。

## 账户同步/自动更新设计前置

同步需要独立服务端：用户身份、设备注册、逐条记录 UUID、变更版本、删除标记、冲突策略、离线队列、导出/删除账户、凭据撤销。当前只有本地数据，不能把 API Key 配置叫“账户登录”。

更新需要独立发布源、签名 manifest、平台/架构/版本选择、下载及签名验证、原子替换/回滚、用户确认和失败恢复。当前仅提供手动构建说明；不访问原软件更新地址，不显示假“已是最新版”。
