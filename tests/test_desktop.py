from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from wordloom.desktop import DesktopError, DesktopSettings, DesktopStore, HotkeyController, parse_hotkey


class FakeHotkeys:
    available = True
    def __init__(self):
        self.active = {}
        self.conflicts = set()
    def register(self, ident, modifiers, key, callback):
        if (modifiers, key) in self.conflicts:
            raise DesktopError('快捷键已被占用')
        self.active[ident] = (modifiers, key, callback)
    def unregister(self, ident):
        self.active.pop(ident, None)
    def close(self):
        self.active.clear()


class DesktopTests(unittest.TestCase):
    def test_parse_and_reserved_keys(self):
        self.assertEqual(parse_hotkey('alt + ctrl + w'), ('Ctrl+Alt+W', 3, ord('W')))
        for value in ['W', 'Shift+W', 'Ctrl+F12', 'Ctrl+Ctrl+W', 'Ctrl+Esc', 'Ctrl+F25', 'Ctrl+F01']:
            with self.subTest(value=value), self.assertRaises(DesktopError):
                parse_hotkey(value)

    def test_conflict_and_failed_save_retain_previous_registration(self):
        backend = FakeHotkeys()
        controller = HotkeyController(backend, lambda: None)
        settings = DesktopSettings()
        controller.configure(settings)
        original = dict(backend.active)
        backend.conflicts.add((3, ord('Q')))
        with self.assertRaises(DesktopError):
            controller.configure(replace(settings, toggle_hotkey='Ctrl+Alt+Q'))
        self.assertEqual(backend.active, original)
        def failed_save():
            raise OSError('disk full')
        with self.assertRaises(OSError):
            controller.configure(replace(settings, toggle_hotkey='Ctrl+Alt+E'), failed_save)
        self.assertEqual(backend.active, original)
        with self.assertRaises(OSError):
            controller.configure(replace(settings, hotkey_enabled=False), failed_save)
        self.assertEqual(backend.active, original)
        controller.configure(replace(settings, toggle_hotkey='Ctrl+Alt+E'))
        self.assertEqual(len(backend.active), 1)
        self.assertEqual(controller.current[1], 'Ctrl+Alt+E')
        controller.configure(replace(settings, hotkey_enabled=False))
        self.assertEqual(backend.active, {})
        controller.close()

    def test_preferences_roundtrip_and_corrupt_preserved(self):
        with TemporaryDirectory() as directory:
            store = DesktopStore(Path(directory))
            self.assertEqual(store.load(), DesktopSettings())
            setting = DesktopSettings('dark', False, 'Ctrl+Shift+T')
            store.save(setting)
            self.assertEqual(DesktopStore(Path(directory)).load(), setting)
            store.path.write_text('broken', encoding='utf-8')
            with self.assertRaises(DesktopError):
                store.load()
            self.assertEqual(store.path.read_text(encoding='utf-8'), 'broken')
