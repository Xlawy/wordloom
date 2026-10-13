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

    def test_two_keys_atomic_conflict_save_failure_swap_and_dispatch(self):
        backend = FakeHotkeys()
        calls = []
        controller = HotkeyController(backend, lambda: calls.append('toggle'), lambda: calls.append('selection'))
        settings = DesktopSettings()
        controller.configure(settings)
        original = dict(backend.active)
        backend.conflicts.add((3, ord('Q')))
        with self.assertRaises(DesktopError):
            controller.configure(replace(settings, toggle_hotkey='Ctrl+Alt+E', selection_hotkey='Ctrl+Alt+Q'))
        self.assertEqual(backend.active, original)
        with self.assertRaises(DesktopError):
            replace(settings, selection_hotkey='Alt+Ctrl+W').validate()
        def fail_save():
            raise OSError('disk full')
        with self.assertRaises(OSError):
            controller.configure(replace(settings, selection_hotkey='Ctrl+Alt+E'), fail_save)
        self.assertEqual(backend.active, original)
        controller.configure(replace(settings, toggle_hotkey='Ctrl+Alt+T', selection_hotkey='Ctrl+Alt+W'))
        self.assertEqual(backend.active, original)  # Swapping actions does not reregister occupied combinations.
        for modifiers, key, callback in backend.active.values():
            callback()
        self.assertEqual(calls, ['selection', 'toggle'])
        controller.close()
        self.assertEqual(backend.active, {})

    def test_older_preferences_preserve_toggle_when_default_selection_would_collide(self):
        import json
        with TemporaryDirectory() as directory:
            store = DesktopStore(Path(directory))
            store.path.write_text(json.dumps({'schema':1,'theme':'dark','hotkey_enabled':True,'toggle_hotkey':'Ctrl+Alt+T'}), encoding='utf-8')
            settings = store.load()
            self.assertTrue(settings.hotkey_enabled)
            self.assertFalse(settings.selection_enabled)
            self.assertEqual(settings.toggle_hotkey, 'Ctrl+Alt+T')
            self.assertEqual(settings.lookup_mode, 'pointer')
            self.assertTrue(settings.pointer_ocr)

    def test_pointer_preferences_roundtrip_and_validation(self):
        with TemporaryDirectory() as directory:
            store = DesktopStore(Path(directory))
            settings = DesktopSettings(lookup_mode='selection', pointer_ocr=False)
            store.save(settings)
            self.assertEqual(store.load(), settings)
            for invalid in (DesktopSettings(lookup_mode='hover'), DesktopSettings(pointer_ocr='true')):
                with self.assertRaises(DesktopError):
                    store.save(invalid)
            self.assertEqual(store.load(), settings)
