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
    'ocr_no_text': '本机 OCR 未识别出文字。请检查识别语言、字号及屏幕内容，或手动粘贴。',
    'ocr_no_hit': '本机 OCR 识别到了文字，但鼠标未命中词框。请把指针移到字形中间重试。',
    'timeout': '取词辅助程序超时，已结束并可重试。',
    'helper': '指针取词辅助程序不可用。请检查 Windows PowerShell 与本机执行策略。',
    'invalid': '取词返回了无效或不匹配的数据，本次未发送模型请求。',
}


STAGES = {
    'init': '组件初始化', 'bridge': '异步接口初始化', 'language': '识别语言初始化',
    'capture': '屏幕捕获', 'decode': '图像解码', 'recognize': '文字识别', 'hitbox': '词框定位',
    'export_lines': '读取识别行', 'export_words': '读取识别词', 'export_box': '读取文字坐标',
}


def pointer_error(code, stage=None, native_line=None, native_hresult=None):
    message = ERRORS.get(code, ERRORS['invalid'])
    if code == 'ocr_error' and stage in ('hitbox', 'export_lines', 'export_words', 'export_box'):
        message = 'OCR 已返回，但读取识别结果失败。请反馈下面的阶段信息。'
    # Only locally defined labels, never echo raw helper errors or screen content.
    if isinstance(stage, str) and stage in STAGES:
        message += f'（阶段：{STAGES[stage]} / {stage}）'
        if (type(native_line) is int and 0 < native_line < 10000 and
                type(native_hresult) is int and -(2**31) <= native_hresult < 2**31):
            message += f' [L{native_line}, HRESULT 0x{native_hresult & 0xffffffff:08X}]'
    raise ApiError('pointer_' + code, message)


def locate_ocr(data, target):
    """Validate primitive OCR geometry and select a word in physical screen space."""
    left, top, lines = data['left'], data['top'], data['lines']
    if any(type(v) is not int or abs(v) > 1000000 for v in (left, top)):
        raise ValueError()
    if not isinstance(lines, list) or len(lines) > 256:
        raise ValueError()
    found = None
    total = 0
    for index, line in enumerate(lines):
        if not isinstance(line, dict):
            raise ValueError()
        text, words = line['text'], line['words']
        if not isinstance(text, str) or len(text) > 4000 or '\0' in text:
            raise ValueError()
        if not isinstance(words, list):
            raise ValueError()
        total += len(words)
        if total > 2048:
            raise ValueError()
        for word in words:
            if not isinstance(word, dict):
                raise ValueError()
            value, box = word['text'], word['box']
            if not isinstance(value, str) or len(value) > 128 or '\0' in value:
                raise ValueError()
            if not isinstance(box, list) or len(box) != 4:
                raise ValueError()
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in box):
                raise ValueError()
            x, y, width, height = box
            if x < 0 or y < 0 or width <= 0 or height <= 0 or x + width > 701 or y + height > 261:
                raise ValueError()
            screen_box = [left + x, top + y, width, height]
            if (found is None and value.strip() and
                    left + x - 2 <= target.x <= left + x + width + 2 and
                    top + y - 2 <= target.y <= top + y + height + 2):
                found = (index, value, screen_box)
    if not total:
        pointer_error('ocr_no_text')
    if found is None:
        pointer_error('ocr_no_hit')
    index, word, box = found
    # Retain the hit line even when neighboring context is unusually long.
    context = lines[index]['text']
    before = lines[index - 1]['text'] if index else ''
    after = lines[index + 1]['text'] if index + 1 < len(lines) else ''
    budget = max(0, (3998 - len(context)) // 2)
    context = '\n'.join(part for part in (before[-budget:] if budget else '', context, after[:budget]) if part)
    return dict(code='ok', word=word, context=context, source='ocr', box=box)


def parse_pointer(raw, target):
    try:
        if len(raw) > 65536:
            raise ValueError()
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get('code'), str):
            raise ValueError()
        if data['code'] == 'ocr_lines':
            data = locate_ocr(data, target)
        code = data['code']
        if code != 'ok':
            pointer_error(code if code in ERRORS else 'invalid', data.get('stage'),
                          data.get('native_line'), data.get('native_hresult'))
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
