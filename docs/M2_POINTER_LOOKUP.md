# M2.2 修正：鼠标指向取词与浮窗

2026-10-13。用户反馈上一版在多个应用中返回“无选区接口”或超时，而且必须先选择，与所需流程不符。用户明确选择“鼠标指向后按快捷键取词”。本阶段纠正该入口，不把上一版选区读取记作验收通过。

## 使用

Windows 原生运行时，将鼠标指向屏幕上一个单词，按 `Ctrl+Alt+T`（沿用已保存的自定义取词快捷键）。无需选择文字。读取成功后，在指针附近显示浮窗，结合上下文调用当前文本模型释义；可修正单词和上下文后重新释义、复制、保存生词及复习。关闭浮窗或按 Esc 取消请求；再次按取词快捷键停止旧请求，读取新位置。失败浮窗提供“打开工作台 / 粘贴”。

“外观与快捷键”可修改快捷键、选择旧的选区翻译模式，以及关闭本机 OCR 回退。默认没有悬停监听或后台翻译。此次不新增 Python 依赖。退出应用后在 Windows 源码目录更新：

```powershell
git pull --ff-only
.\.venv-win\Scripts\python.exe -m wordloom
```

上述使用此前已安装的 Windows 环境，不能复用 WSL `.venv`。尚无新的 EXE 安装包。

## 实现与边界

- `platforms/pointer.py` 在按键时记录物理鼠标坐标、目标窗口和前台窗口。后台可复用 PowerShell 辅助进程运行原生操作，管道交换带请求 ID 的数据；超时、取消会终止辅助进程，迟到结果不复用。启动时只预热组件，不读取屏幕。
- `resources/pointer_worker.ps1` 优先 `AutomationElement.FromPoint → TextPattern.RangeFromPoint → Word`，必须命中单词矩形；上下文取段落，长段落改取邻近词，最多 4000 字符。不是 `GetSelection`，无需选中。
- 文本接口不可用/超时后，启用回退时在本机截取指针附近至多 700×260 物理像素，用 Windows OCR 识别，按词框命中指针。上下文为命中行及相邻两行，不保证包含完整句子。英文 OCR 语言优先，否则尝试用户语言；组件或语言缺失明确报错。可在 Windows 语言设置中安装相应 OCR 语言功能。
- 截图仅在内存处理，不上传、不落盘。识别后的单词和上下文发送到用户当前文本模型；不要求模型支持图片，也不使用配置中的云端 OCR 服务。云端图像协议仍是独立能力。
- 可复用进程减少每次冷启动；UIA 等待预算 1.5 秒、OCR 8 秒，整个取词任务有总时限。它们是超时设置，不是性能实测值。PowerShell `ExecutionPolicy Bypass` 仅用于该子进程，不改变系统策略；组织策略仍可能阻止脚本。
- `ui_lookup.py` 使用共用 Client、凭据库、Library 和复习逻辑。浮窗设置不主动激活；编辑后必须重新释义才能保存，取消的部分输出不入库。截图完成后才出现浮窗，以免遮住待识别区域。取词等待期间再次按快捷键可重新触发。
- 原生 UIA 若明确标识密码输入则停止、不回退截图。屏幕保护、被遮挡文字、小字号、特殊字体、语言包、权限差异和软件自身实现仍可能使取词失败。当前不截取隐藏窗口；不承诺所有软件兼容。浮窗显示及 DPI 要在 Windows 验证。
- macOS 当前不支持指针读取、本机 OCR 或全局快捷键；只复用数据、模型和浮窗代码，原生适配与测试均待完成。

## 对照证据（静态，不是原软件运行验证）

完整分析留在工作区 `outputs/pointer-followup-evidence.md`，输入样本未改动。Git 仓库不包含分析样本，以下列出可定位证据。

| 项目 | 原包证据 | 本应用实现/验收 |
|---|---|---|
| 指针入口 | `outputs/code-metadata/app.pointer_controller.json`，`PointerController.trigger:144` 文档及 `_run:165` 引用鼠标坐标、截图、lookup | 默认快捷键指向取词；用户指定，不需要拖选 |
| 单词与上下文 | `app.pointer_lookup.json` 文档说明鼠标位置的 word/sentence/paragraph；仅说明设计，不证明所有软件有效 | UIA 段落或 OCR 邻近行；浮窗允许修正，原生需核对准确性 |
| 图像回退 | `app.pointer_capture.json` 的 `_print_window:305`、`capture_window:329` 和 `capture_display:387` | 独立实现可见屏幕局部捕获；没有复制 PrintWindow 路径或原 OCR 权重 |
| 浮窗 | `app.translation_preview.json` 的 `TranslationPreview.present:510` 及模块文档描述原地、不激活主窗口 | 独立 Qt 浮窗→释义→收藏→复习；共用控件测试通过，焦点原生待验 |
| 触发方式 | `app.pointer_trigger.json` 模块字符串描述轻按 Alt，不能证明无键悬停 | 用户选择可配置组合快捷键；不是照搬原软件 Alt 时序 |

技术接口参考：[Microsoft 文本范围扩展](https://learn.microsoft.com/en-us/dotnet/api/system.windows.automation.text.textpatternrange.expandtoenclosingunit)、[Microsoft 指针下取词示例](https://devblogs.microsoft.com/oldnewthing/20150216-00/?p=44673)、[Windows OCR 官方示例](https://github.com/Microsoft/Windows-universal-samples/blob/main/Samples/OCR/cs/OcrFileImage.xaml.cs)。这些资料不代表本应用已通过原生测试。

## Windows 验收与诊断

在 Windows PowerShell 中运行；诊断脚本给出 5 秒切换窗口，将鼠标停在普通英文单词上，不选择，不改变前台。输出来源、长度和耗时，不输出原文、不请求模型。

```powershell
.\.venv-win\Scripts\python.exe scripts\check_pointer.py --no-ocr
.\.venv-win\Scripts\python.exe scripts\check_pointer.py --ocr-only
.\.venv-win\Scripts\python.exe scripts\check_pointer.py
.\.venv-win\Scripts\python.exe scripts\validate.py --output validation\windows-pointer
```

`--ocr-only` 是直接截图诊断，绕过 UIA，请仅指向用于测试的普通文本。测试时记录应用名/版本、Windows 版本、显示缩放、诊断输出和具体失败步骤，不必提供隐私原文。

- [ ] 记事本、浏览器正文、PDF 各自：不选中，指向词语触发，词语与上下文正确，浮窗不唤起主窗口、不抢焦点。
- [ ] 对文本接口失败的软件：`--ocr-only` 返回 `source=ocr`；实际快捷键自动回退，浮窗标识 OCR，纠正后重新释义并保存。
- [ ] 只有触发快捷键才发送模型请求；已有剪贴板内容不变；错误后粘贴入口可用。
- [ ] 连续两次触发、取词中切前台、释义中关闭/Esc、重新取词：无旧结果覆盖，无取消后入库，无辅助进程长期残留。
- [ ] 明暗主题、100%/150%/200% 缩放、多屏负坐标及屏幕边缘：命中正确，浮窗可见且可编辑。
- [ ] OCR 语言未安装时出现明确提示；关闭 OCR 回退后只报文本接口错误，不截图。
- [ ] 保存单词、原文上下文和释义后重启仍存在，复习进度保存。模型断网/取消后可重新释义。

Windows 原生以上项目均待实测；本轮 agent 的 PowerShell 互操作报 `WSL ERROR: UtilBindVsockAnyPort:317: socket failed 1`。WSL 测试中的原生结果由替身提供，不能据此声称 Windows OCR/UIA 通过。HTTP 套接字检查仍受环境限制，详见 VALIDATION.md。

此入口原生验收通过后，再实现用户框选区域 → OCR → 修正全文 → 翻译，随后做系统托盘与退出行为。本次局部指针 OCR 不代表已经实现区域截图工具。

## Windows 用户反馈与 OCR 修复（2026-10-13）

用户反馈 Notion、Chrome、终端可以取词，微信和 WPS 报“本机截图/OCR 未成功”。这是部分应用的实际使用反馈；尚未确认各成功应用走 UIA 还是 OCR，也未确认失败应用的文档类型、语言和 DPI。

检查发现 OCR 词框转换 `@($left+$r.X, $top+$r.Y, ...)` 未按坐标分组；PowerShell 逗号优先于加法，会把数组参与运算。已抽出 `GetScreenBox`，对每项加法分别加括号，修复明确的代码缺陷。这可能解释上述失败，但不能据此宣称微信/WPS 已通过复测。依据：[Microsoft 运算优先级](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_operator_precedence)。

错误现区分组件/语言初始化、截图、解码、识别、词框定位；无文字与鼠标未命中分别提示。只输出固定阶段标签，不暴露原始异常、截图、识别内容或服务凭据。仍以 OCR 实际结果为准，不把泛化错误认定为缺权限/语言包。

更新并重启后先复测微信、WPS。若仍失败，提供完整阶段提示，或运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\check_pointer_worker.ps1
.\.venv-win\Scripts\python.exe scripts\check_pointer.py --ocr-only
```

第一条从生产脚本 AST 提取坐标转换及命中函数，实际执行正负坐标/小数/命中和未命中回归，不读取屏幕；第二条实际测试本机截图 OCR，需在倒计时内将指针放到待测普通文字。Windows 脚本测试尚未在 agent 执行成功，互操作仍受 socket 限制。
