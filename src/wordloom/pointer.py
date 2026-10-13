"""Pointer lookup data and validation, independent of native or Qt integration."""
from dataclasses import dataclass
import json
import math
from .providers import ApiError


@dataclass(frozen=True)
class PointerTarget:
    x: int
    y: int
    window: int
    pid: int
    foreground: int


@dataclass(frozen=True)
class PointerText:
    word: str
    context: str
    source: str
    box: tuple[float, float, float, float]


ERRORS = {
    'empty': '鼠标位置没有识别到文字。请将指针放在字上重试，或手动粘贴。',
    'unsupported': '目标没有提供指针文本接口。可启用本机 OCR 回退后重试。',
    'protected': '目标是受保护输入，不读取或截图。请在普通文本上取词。',
    'changed': '取词期间目标窗口已变化，本次已停止。',
    'ocr_missing': '本机 Windows OCR 或识别语言不可用。请在 Windows 语言设置中安装所需语言的 OCR 功能，或手动粘贴。',
    'ocr_error': '本机截图/OCR 未成功。请检查屏幕权限、受保护内容及识别语言，或手动粘贴。',
    'timeout': '取词辅助程序超时，已结束并可重试。',
    'helper': '指针取词辅助程序不可用。请检查 Windows PowerShell 与本机执行策略。',
    'invalid': '取词返回了无效或不匹配的数据，本次未发送模型请求。',
}


def pointer_error(code):
    raise ApiError('pointer_' + code, ERRORS.get(code, ERRORS['invalid']))


def parse_pointer(raw, target):
    try:
        if len(raw) > 65536:
            raise ValueError()
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get('code'), str):
            raise ValueError()
        code = data['code']
        if code != 'ok':
            pointer_error(code if code in ERRORS else 'invalid')
        word, context, source, box = (data[k] for k in ('word', 'context', 'source', 'box'))
        if not isinstance(word, str) or not word.strip() or len(word) > 128 or '\0' in word:
            raise ValueError()
        if not isinstance(context, str) or len(context) > 4000 or '\0' in context:
            raise ValueError()
        if source not in ('uia', 'ocr') or not isinstance(box, list) or len(box) != 4:
            raise ValueError()
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in box):
            raise ValueError()
        x, y, w, h = box
        if w <= 0 or h <= 0 or w > 10000 or h > 1000:
            raise ValueError()
        if not (x - 3 <= target.x <= x + w + 3 and y - 3 <= target.y <= y + h + 3):
            pointer_error('empty')
        return PointerText(word.strip(), context.strip(), source, tuple(box))
    except (KeyError, TypeError, ValueError, UnicodeError):
        pointer_error('invalid')
