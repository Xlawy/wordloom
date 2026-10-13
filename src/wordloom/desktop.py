"""Shared preferences and transactional hotkey changes; native code is separate."""
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from .config import atomic_write


class DesktopError(ValueError):
    pass


def parse_hotkey(value):
    if not isinstance(value, str):
        raise DesktopError('快捷键必须是文本。')
    parts = [p.strip().upper() for p in value.split('+')]
    modifiers = {'CTRL': 2, 'ALT': 1, 'SHIFT': 4, 'WIN': 8}
    if len(parts) < 2 or any(p not in modifiers for p in parts[:-1]) or len(set(parts[:-1])) != len(parts[:-1]):
        raise DesktopError('格式示例 Ctrl+Alt+W；修饰键支持 Ctrl、Alt、Shift、Win。')
    flags = sum(modifiers[p] for p in parts[:-1])
    if not flags & (1 | 2 | 8):
        raise DesktopError('至少包含 Ctrl、Alt 或 Win，不能仅用 Shift。')
    key = parts[-1]
    if len(key) == 1 and key in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
        vk = ord(key)
    elif key.startswith('F') and key[1:].isdigit() and 1 <= int(key[1:]) <= 24 and key == f'F{int(key[1:])}':
        vk = 0x70 + int(key[1:]) - 1
    else:
        raise DesktopError('主键支持 A–Z、0–9、F1–F24（F12 为系统保留，不可使用）。')
    if vk == 0x7B:
        raise DesktopError('F12 是系统保留键，请选择其他组合。')
    normalized = '+'.join([p.title() if p != 'CTRL' else 'Ctrl' for p in modifiers if flags & modifiers[p]] + [key])
    return normalized, flags, vk


@dataclass(frozen=True)
class DesktopSettings:
    theme: str = 'system'
    hotkey_enabled: bool = True
    toggle_hotkey: str = 'Ctrl+Alt+W'

    def validate(self):
        if self.theme not in ('system', 'light', 'dark') or type(self.hotkey_enabled) is not bool:
            raise DesktopError('外观或快捷键设置无效。')
        parse_hotkey(self.toggle_hotkey)


class DesktopStore:
    def __init__(self, directory: Path):
        self.path = directory / 'desktop.json'

    def load(self):
        if not self.path.exists():
            return DesktopSettings()
        try:
            if self.path.stat().st_size > 4096:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or data.pop('schema', None) != 1:
                raise ValueError()
            settings = DesktopSettings(**data)
            settings.validate()
            return settings
        except (ValueError, TypeError):
            raise DesktopError('desktop.json 无效；原文件已保留。可在外观与快捷键设置中重新保存。') from None

    def save(self, settings):
        settings.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, json.dumps({'schema': 1, **asdict(settings)}, ensure_ascii=False, indent=2))


class HotkeyController:
    """Reserve a replacement before saving and releasing the working shortcut."""
    def __init__(self, backend, callback):
        self.backend, self.callback = backend, callback
        self.current = None  # (id, normalized shortcut)
        self.next_id = 0x5740

    def configure(self, settings, persist=lambda: None):
        settings.validate()
        name, modifiers, key = parse_hotkey(settings.toggle_hotkey)
        if settings.hotkey_enabled and not self.backend.available:
            raise DesktopError(self.backend.reason)
        if settings.hotkey_enabled and self.current and self.current[1] == name:
            persist()
            return
        pending = None
        if settings.hotkey_enabled:
            pending = self.next_id
            self.backend.register(pending, modifiers, key, self.callback)
        try:
            persist()
        except Exception:
            if pending is not None:
                self.backend.unregister(pending)
            raise
        if self.current:
            self.backend.unregister(self.current[0])
        self.current = (pending, name) if pending is not None else None
        self.next_id = 0x5741 if pending == 0x5740 else 0x5740

    def close(self):
        if self.current:
            self.backend.unregister(self.current[0])
            self.current = None
        self.backend.close()
