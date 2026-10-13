# 功能对照与验收

> 当前状态：用户已确认 Windows 主题与唤起/隐藏快捷键通过；随后反馈选区读取兼容性不足。M2.2 现改为鼠标指向后按快捷键，UIA 指针读取 → 本机 OCR 回退 → 浮窗释义/收藏。Windows 新增原生能力待验收，macOS 尚未实现。详见 [当前实现、边界和验收](M2_POINTER_LOOKUP.md)。下文此前阶段记录中的“待验收/下一步”保留历史含义，以本条和最新验证记录为准。

来源 `../../outputs/code-metadata/`；行号是内嵌源标识，不是已恢复原始源文件。以下“证实”均为静态证据，未经原软件运行观察。新应用实现不依赖原软件服务、品牌或资源。

| 功能 | 已证实的静态证据 | 未验证的行为/推测 | WordLoom 拟实现 | 状态/验收 |
|---|---|---|---|---|
| 主窗口 | app.main.main:182 引用 QApplication/MainWindow/exec | 初始化顺序/界面细节 | 独立翻译、词库、复习页 | M1；UI 启动和闭环测试 |
| 自定义 API | 原包 lexisnap_api 引用自有后端 | 原软件没有通用 API 配置的证据 | 多配置/独立 Key/协议/模型/参数/提示词 | M1 新能力；配置持久化和 mock 服务测试 |
| 输入/翻译 | translation_service.translate:186、request_for:61 含请求与结果名 | 线上模型与重试策略未知 | 粘贴文本+上下文，SSE/JSON，取消/复制/手动重试 | M1；流分片、HTTP 错误、取消/超时测试 |
| 取词 | HotkeyManager:312、PointerController.trigger:144 | Alt 时序/定位/冷却未运行验证 | 平台快捷键/选区适配 | M2；两系统真实应用逐项验收 |
| OCR | ocr._get_engine:9 引用 RapidOCR，3 个 ONNX 模型 | 默认参数是否覆盖未知 | 独立 OCR API 配置，显式图像能力；随后本地 OCR | M1 配置基础与协议边界；M2 截图联动 |
| 词库 | db.get_conn:242/init_db:255、records/collections SQL | 全部迁移/事务行为未知 | SQLite 条目、上下文、结果 CRUD/搜索/JSON+CSV 导入导出 | M1；事务、重启持久化、无密钥导出测试 |
| 复习 | ReviewScheduler.rate:129 引用 fsrs 和保存方法 | 精确评分映射未验证 | 自有简单间隔算法，显示答案后评分；持久化到期/历史 | M1；明确不是 FSRS；固定时钟测试 |
| 发音 | PronunciationPlayer.play:304 和音频 API 路径 | 音频源/缓存效果未知 | 系统本地 TTS，不调用原后端 | M3；平台音频验收 |
| 托盘 | QSystemTrayIcon 引用和图像资源存在 | 驻留/退出语义未知 | 平台托盘与关闭偏好 | M3；平台验收 |
| 凭据 | auth_store 的 WindowsCredentialStore/Cred* 引用 | 所有配置分支未验证 | 新应用原生凭据库，明确会话模式 | M1；假凭据库测试，原生库待验收 |
| 账户同步 | API 有验证码/密码/账户路径 | 不证明存在词库同步 | 离线数据先行；另设计账户与冲突协议 | M4 未实现；无假入口 |
| 自动更新 | updater 有下载、SHA256、Popen 符号 | 全部分支安全性未验证 | 独立签名发布、平台构建和回滚设计 | M4 未实现；无假入口 |

## 本轮交付状态（2026-10-13）

| M1 内容 | 实现位置 | 实际状态与验收 |
|---|---|---|
| 主窗口/工作台/设置 | `src/wordloom/ui.py`、`ui_settings.py` | 原有 6 项控件测试及 offscreen 启动已通过；新增 HTTP+GUI 联合用例待普通终端执行；Windows 待验收 |
| 多配置、参数、提示词和独立 OCR 配置 | `config.py`、`ui_settings.py` | 核心配置持久化及校验测试通过；表单操作测试通过，真实图像服务待验收 |
| 系统凭据/会话凭据 | `platforms/credentials.py` | 注入凭据库、隔离、失败不降级、会话清理测试通过；WinVault/Keychain 真机待验收 |
| Chat Completions、SSE、模型列表、取消与错误 | `providers.py`、`network.py` | 内存 HTTP 边界测试通过，实际 QtCore 后台任务测试通过；普通终端真实 loopback HTTP 的 6 项测试通过；真实模型服务待验收 |
| SQLite 词库/搜索/编辑/删除/交换 | `library.py` | 持久化、事务、重复项、长文本、JSON/CSV 往返测试通过；GUI 控件操作已通过；Windows 待验收 |
| 最小间隔复习 | `library.py`、`ui.py` | 固定时钟下排期、重复评分拒绝、进度重启保存测试通过；控件揭示/评分及新增跨进程持久化测试通过；Windows 待验收 |
| 交付与构建 | `README.md`、`scripts/validate.py`、`scripts/build_desktop.py` | 精确启动/验证/原生构建命令已交付；Windows/macOS 未构建未验收 |

普通 WSL 原有 49 项核心/HTTP 和 6 项控件测试通过。本轮 agent 又验证 44 项核心（含新增进程重启）和 6 项控件，套接字相关检查环境跳过。Windows 原生凭据脚本、安装入口及验收表已准备，尚未执行。**真实模型和 Windows 核心验收未完成，不进入 M2；macOS 仅共用代码与凭据适配，原生实现/验证没有新增。** 详见 `VALIDATION.md`、`WINDOWS_ACCEPTANCE.md`。

## 后续更新：主题与 M2.1

用户反馈 Windows 启动与原有功能正常。`theme.py` 修复明暗混用，新增完整主题切换；`desktop.py`/`ui_desktop.py` 提供独立偏好及事务式快捷键修改，`platforms/hotkeys.py` 实现 Windows 注册与事件适配。当前仅“全局唤起/隐藏”代码完成，**不能等同已实现选中文字或截图**。8 项界面及 47 项核心测试通过，Windows 物理按键验收待执行。macOS 全局快捷键尚未实现，主题未原生验证。详见 [M2.1](M2_WINDOWS_HOTKEY.md)。

## M2.2 更新

M2.1 已获用户 Windows 原生通过反馈。新增 `platforms/selection.py` 与 `resources/read_selection.ps1`，读取外部焦点控件的 UIA 选区，不操作剪贴板。共用快捷键控制器支持两组独立配置与事务式修改；工作台复用现有模型、词库和复习。选词闭环替身测试及辅助进程生命周期测试通过；Windows 应用兼容性待验收。macOS 选词未实现。下一项仍为截图/OCR，尚未开始。见 [M2.2](M2_SELECTION.md)。
