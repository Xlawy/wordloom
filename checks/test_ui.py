"""Qt Widgets acceptance suite, run in its own process (separate from QtCore tests).

Requests use the real Client with an in-memory HTTP boundary. Actual loopback
network is independently covered by tests.test_live_http.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch


class UIAcceptance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError as exc:
            raise unittest.SkipTest(f"GUI_ENVIRONMENT_UNAVAILABLE: {exc}") from None
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        from wordloom.config import ConfigStore, Profile, Settings
        from wordloom.library import Library
        from wordloom.platforms.credentials import Credentials
        from wordloom.ui import MainWindow
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name)
        self.profile = Profile(name="测试服务", base_url="http://127.0.0.1:8765/v1", model="custom-test")
        self.store = ConfigStore(self.path)
        self.settings = Settings([self.profile], self.profile.id)
        self.store.save(self.settings)
        self.library = Library(self.path / "library.sqlite3")
        self.credentials = Credentials()
        from wordloom.platforms.hotkeys import UnsupportedHotkeys
        with patch("wordloom.ui.create_hotkeys", return_value=UnsupportedHotkeys()):
            self.window = MainWindow(self.store, self.settings, self.library, self.credentials)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.library.close()
        self.temp.cleanup()

    def until(self, condition, seconds=3):
        from PySide6.QtTest import QTest
        deadline = time.monotonic() + seconds
        while not condition() and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertTrue(condition(), "UI deadline exceeded")

    def translate(self, response=None):
        from tests.test_network import Connection, Response, json_result
        self.window.input.setPlainText("serendipity")
        self.window.context.setPlainText("a lucky encounter")
        connection = Connection(response or Response(json_result("机缘巧合；意外的好运。")))
        with patch("wordloom.network.http.client.HTTPConnection", return_value=connection):
            self.window.translate_button.click()
            self.until(lambda: self.window.job is not None and not self.window.job.active)
        return connection

    def test_translate_save_review_copy_and_reopen(self):
        self.translate()
        self.assertTrue(self.window.save_button.isEnabled())
        self.assertIn("机缘巧合", self.window.result.toPlainText())
        from PySide6.QtWidgets import QPushButton
        copy_button = next(b for b in self.window.findChildren(QPushButton) if b.text() == "复制结果")
        copy_button.click()
        self.assertEqual(self.app.clipboard().text(), self.window.result.toPlainText())
        self.window.save_button.click()
        self.assertEqual(len(self.library.search()), 1)
        entry = self.library.search()[0]
        self.assertEqual(entry.context, "a lucky encounter")
        self.window.tabs.setCurrentIndex(2)
        self.assertEqual(self.window.answer.toPlainText(), "")
        self.assertFalse(self.window.grade_buttons[2].isEnabled())
        self.window.reveal_button.click()
        self.assertIn("机缘巧合", self.window.answer.toPlainText())
        self.window.grade_buttons[2].click()
        self.assertEqual(self.library.get(entry.id).repetitions, 1)
        from wordloom.library import Library
        second = Library(self.path / "library.sqlite3")
        try:
            self.assertEqual(second.get(entry.id).repetitions, 1)
            self.assertEqual(second.due_entries(), [])
        finally:
            second.close()

    def test_error_retry_and_no_failed_save(self):
        from tests.test_network import Response
        self.translate(Response(status=401))
        self.assertIn("鉴权失败", self.window.request_status.text())
        self.assertFalse(self.window.save_button.isEnabled())
        self.assertTrue(self.window.retry_button.isEnabled())
        from tests.test_network import Connection, json_result
        with patch("wordloom.network.http.client.HTTPConnection", return_value=Connection(Response(json_result("重试成功")))):
            self.window.retry_button.click()
            self.until(lambda: not self.window.job.active)
        self.assertEqual(self.window.result.toPlainText(), "重试成功")
        self.assertTrue(self.window.save_button.isEnabled())

    def test_cancel_and_continue_using_window(self):
        import threading
        from tests.test_network import Connection, Response
        c = Connection(Response())
        c.response.read1 = lambda size: (c.shutdown_event.wait(2), b"")[1]
        self.window.input.setPlainText("hello")
        with patch("wordloom.network.http.client.HTTPConnection", return_value=c):
            self.window.translate_button.click()
            self.window.cancel_button.click()
            self.assertFalse(self.window.job.active)
            self.assertTrue(self.window.input.isEnabled())
            self.assertFalse(self.window.save_button.isEnabled())
            self.window.job.thread.join(2)
            self.app.processEvents()
        self.assertIn("已取消", self.window.request_status.text())

    def test_library_search_edit_export_import_delete(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        self.translate()
        self.window.save_button.click()
        self.window.tabs.setCurrentIndex(1)
        self.window.search.setText("机缘")
        self.assertEqual(self.window.table.rowCount(), 1)
        self.window.table.selectRow(0)
        def change():
            dialog = self.app.activeModalWidget()
            dialog.meaning.setPlainText("修改后的释义")
            dialog.accept()
        QTimer.singleShot(0, change)
        self.window.edit_entry()
        self.window.search.clear()
        self.assertEqual(self.library.search()[0].meaning, "修改后的释义")
        export = self.path / "export.json"
        with patch.object(QFileDialog, "getSaveFileName", return_value=(str(export), "JSON")):
            self.window.export_library()
        self.assertTrue(export.exists())
        self.window.table.selectRow(0)
        with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            self.window.delete_entry()
        self.assertEqual(self.library.search(), [])
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(export), "JSON")):
            self.window.import_library()
        self.assertEqual(len(self.library.search()), 1)

    def test_settings_save_separate_ocr_and_key(self):
        from wordloom.ui_settings import SettingsDialog
        dialog = SettingsDialog(self.store, self.settings, self.credentials)
        dialog.new_profile()
        dialog.name.setText("另一个服务")
        dialog.url.setText("http://127.0.0.1:9988/v1")
        dialog.model.setEditText("my-vision-model")
        dialog.purpose.setCurrentIndex(dialog.purpose.findData("ocr"))
        dialog.vision.setChecked(True)
        dialog.key.setText("test-secret-only")
        dialog.session.setChecked(True)
        self.assertTrue(dialog.save_profile())
        settings = self.store.load()
        self.assertEqual(settings.active("ocr").model, "my-vision-model")
        self.assertEqual(settings.active().id, self.profile.id)
        self.assertNotIn("test-secret-only", self.store.path.read_text(encoding="utf-8"))
        self.assertEqual(self.credentials.get(settings.active("ocr").credential_id), "test-secret-only")
        dialog.close()

    def test_settings_connection_and_model_list(self):
        from wordloom.ui_settings import SettingsDialog
        from tests.test_network import Response, Connection, json_result
        dialog = SettingsDialog(self.store, self.settings, self.credentials)
        with patch("wordloom.network.http.client.HTTPConnection", return_value=Connection(Response(b'{"data":[{"id":"manual-model"}]}'))):
            dialog.models_button.click()
            self.until(lambda: dialog.job is not None and not dialog.job.active)
        self.assertIn("1 个模型", dialog.status.text())
        with patch("wordloom.network.http.client.HTTPConnection", return_value=Connection(Response(json_result()))):
            dialog.test_button.click()
            self.until(lambda: not dialog.job.active)
        self.assertIn("连接成功", dialog.status.text())
        dialog.dirty = False
        dialog.close()

    def test_actual_http_stream_cancel_then_save_and_review(self):
        import socket
        import threading
        from scripts.mock_server import MockServer
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            self.skipTest(f"ENVIRONMENT_RESTRICTED: local sockets: {exc}")
        server = MockServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            self.profile.base_url = server.base_url
            self.profile.model = "mock-slow-stream"
            self.window.input.setPlainText("serendipity " * 30)
            self.window.translate_button.click()
            self.until(lambda: bool(self.window.result.toPlainText()))
            self.assertTrue(self.window.job.active)
            self.window.cancel_button.click()
            self.window.job.thread.join(2)
            self.assertFalse(self.window.job.thread.is_alive(), "cancel must stop socket worker")
            self.app.processEvents()
            self.assertFalse(self.window.save_button.isEnabled())
            self.assertEqual(self.library.search(), [])
            self.profile.model = "mock-stream"
            self.window.input.setPlainText("serendipity")
            self.window.translate_button.click()
            self.until(lambda: not self.window.job.active)
            self.assertIn("[MOCK", self.window.result.toPlainText())
            self.assertIn("serendipity", self.window.result.toPlainText())
            self.window.save_button.click()
            entry = self.library.search()[0]
            self.window.tabs.setCurrentIndex(2)
            self.window.reveal_button.click()
            self.window.grade_buttons[2].click()
            self.assertEqual(self.library.get(entry.id).repetitions, 1)
        finally:
            if self.window.job and self.window.job.active:
                self.window.cancel_request()
                self.window.job.thread.join(2)
            server.shutdown()
            server.server_close()
            thread.join(2)

    def test_desktop_dialog_hotkey_conflict_toggle_and_restart_preferences(self):
        from wordloom.desktop import DesktopError, HotkeyController, DesktopStore
        from wordloom.platforms.hotkeys import WindowsHotkeys
        from wordloom.ui_desktop import DesktopDialog
        class API:
            def __init__(self):
                self.active = {}
                self.foregrounds = []
            def register(self, ident, modifiers, key):
                if key == ord('Q'):
                    raise DesktopError('快捷键已被占用')
                self.active[ident] = key
            def unregister(self, ident):
                self.active.pop(ident, None)
            def foreground(self, handle):
                self.foregrounds.append(handle)
        api = API()
        backend = WindowsHotkeys(api)
        self.window.hotkeys.close()
        self.window.hotkeys = HotkeyController(backend, self.window.toggle_window)
        self.window.hotkeys.configure(self.window.desktop_settings)
        try:
            dialog = DesktopDialog(self.window)
            dialog.theme.setCurrentIndex(dialog.theme.findData('dark'))
            dialog.shortcut.setText('Ctrl+Alt+E')
            dialog.save()
            settings = DesktopStore(self.path).load()
            self.assertEqual((settings.theme, settings.toggle_hotkey), ('dark', 'Ctrl+Alt+E'))
            ident = self.window.hotkeys.current[0]
            self.window.activateWindow()
            self.app.processEvents()
            self.assertTrue(backend.dispatch(0x0312, ident))
            self.assertFalse(self.window.isVisible())
            backend.dispatch(0x0312, ident)
            self.assertTrue(self.window.isVisible())
            self.assertTrue(api.foregrounds)
            conflict = DesktopDialog(self.window)
            conflict.shortcut.setText('Ctrl+Alt+Q')
            conflict.save()
            self.assertIn('已被占用', conflict.error.text())
            self.assertEqual(DesktopStore(self.path).load(), settings)
            self.assertEqual(self.window.hotkeys.current[0], ident)
            conflict.reject()
        finally:
            self.window.hotkeys.close()
            self.window.theme.apply('system')


if __name__ == "__main__":
    unittest.main()
