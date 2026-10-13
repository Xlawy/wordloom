# 语笺 WordLoom：开发方案与里程碑

> 当前状态：用户已确认 Windows 主题与唤起/隐藏快捷键通过；随后反馈选区读取兼容性不足。M2.2 现改为鼠标指向后按快捷键，UIA 指针读取 → 本机 OCR 回退 → 浮窗释义/收藏。Windows 新增原生能力待验收，macOS 尚未实现。详见 [当前实现、边界和验收](M2_POINTER_LOOKUP.md)。下文此前阶段记录中的“待验收/下一步”保留历史含义，以本条和最新验证记录为准。

## 决策（实现前记录）

独立编写 Python 3.11+ / PySide6 Qt Widgets 桌面软件；SQLite 保存本地词库和复习记录，JSON 仅保存不含密钥的模型配置。原样本的 Python/Qt 结构证明这条路线可行，但不作为复制代码的来源。应用名、界面和资源自行设计。

共用领域层、协议层和 UI；`platforms/` 隔离系统凭据、快捷键、选区、截图、托盘、发音及权限接口。首轮真正实现凭据适配；未完成的系统能力不展示可点击的假按钮。账户同步和更新仅在路线图中。

模型协议首轮为 OpenAI-compatible **Chat Completions**，不是任意 HTTP 地址自动识别，也不要求 OpenAI 账号。用户填写完整 API 根路径（如 `https://服务商/v1`）；模型手输优先，GET models 是可选辅助。温度/长度参数可关闭，长度字段可选择。文本与 OCR 使用独立用途的配置，OCR 必须显式开启图像能力才允许图片请求。

请求由后台工作线程运行，UI 通过 Qt 信号更新。底层使用 Python 标准库 HTTPS/HTTP，提供总截止时间、有限响应大小、SSE 解析、连接关闭和取消信号。没有自动重试；失败后由用户决定重试。禁止跟随重定向携带密钥。网络错误不回显响应体或请求头，避免服务端回显 Key。

API Key 通过 Windows Credential Manager / macOS Keychain（keyring 原生后端）存取，不接受明文文件后端。没有系统凭据库时可以明确选择仅会话使用；无 Key 的本机服务也可使用。修改服务地址或用途时隔离凭据标识，避免旧 Key 被发往新地址。测试只用临时目录和本地模拟 HTTP 服务。

## 里程碑

1. **M1（本轮）**：真实 API 配置增删改/切换、模型列表、连接测试、提示词、流式/非流式翻译与取消；文本输入→结果→词库 CRUD/搜索/JSON+CSV 交换→最小间隔复习闭环。完成核心测试、可执行范围内的 UI 检查、构建和原生验收说明。
2. **M1.1（当前）**：根据普通 WSL 日志补验现有流程，在独立 `.venv-win` 中完成 Windows 原生窗口、真实 API、取消、原生凭据及重启持久化验收；以 WINDOWS_ACCEPTANCE.md 为门槛。未通过前不启动 M2。
3. **M2**：Windows/macOS 全局快捷键与选区读取（先权限与能力探测）、区域截图、可单独选择 OCR 配置；先选图 OCR 验证图像模型协议，再平台截图。对取消/剪贴板恢复/多屏缩放做原生测试。
4. **M3**：本机 TTS、托盘、启动设置、可选本地 OCR 引擎、词单/导出扩展、复习算法升级。只承诺实际实现和验收的功能。
5. **M4**：另行设计同步冲突/账户身份/服务端凭据隔离；更新需签名发布清单、平台签名、公证、回滚策略。无原软件后端连接，无模拟登录/更新按钮。

## 依据与验证范围

阅读 `../../outputs/phase1-static-report.md`，并核对 code-metadata 中 capture_controller、ocr、translation_service、db、review_scheduler、pronunciation、auth_store、updater 的指定函数。现有名称/常量只能证实静态结构，不能把它们当完整运行行为。此次不需要 Ghidra 或完整反编译。

开发宿主是 WSL2 Linux/Python 3.13.5。开工时无 PySide6/pip，系统 venv 缺 ensurepip，下载请求受环境网络限制。随后用户已在普通终端把依赖安装到项目 `.venv`；继续开发直接使用该环境，不重复安装。实际确认 PySide6 6.12.0、keyring 25.7.0 以及 QtCore 可用；普通终端已提交 HTTP/GUI/启动通过日志；agent 环境仍禁止套接字，但 Qt Widgets 和 offscreen 启动现已可用。Windows 互操作实际报 UtilBindVsockAnyPort socket failed 1，不能据 WSL 测试宣布 Windows 通过。详细状态见 VALIDATION.md，不写“双平台通过”。

协议资料（仅格式参考，不推导第三方兼容性）：

- [Chat Completions 请求](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)
- [SSE 流式事件](https://developers.openai.com/api/reference/resources/chat/subresources/completions/streaming-events)
- [Qt 网络取消语义](https://doc.qt.io/qtforpython-6/PySide6/QtNetwork/QNetworkReply.html)

验收以 `docs/FEATURE_MATRIX.md`、`docs/VALIDATION.md`、`docs/NATIVE_CHECKLIST.md` 的最终状态为准。

## 最新执行顺序

用户已报告 Windows 原有功能正常。本轮先修复主题并实现 M2.1 全局快捷键（代码及共用测试完成，Windows 物理按键验收待完成）。后续严格依次为选词翻译、截图 OCR/修正/翻译、托盘退出；每项先端到端验收再继续。M2.1 原生门槛和 macOS 单独状态见 M2_WINDOWS_HOTKEY.md。

M2.1 已由用户确认通过。M2.2 当前实现为 UI Automation 读取选区 → 当前模型翻译 → 收藏/复习，失败转手动粘贴；只读选区，不写剪贴板。原生验收后才做截图/OCR，再做托盘。详见 M2_SELECTION.md。
