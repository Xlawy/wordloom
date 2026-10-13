from pathlib import Path
from tempfile import TemporaryDirectory
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from wordloom.config import ConfigStore, Profile, Settings
from wordloom.library import Library
from wordloom.platforms.credentials import Credentials
from wordloom.platforms.hotkeys import UnsupportedHotkeys
from wordloom.platforms.pointer import UnsupportedPointer
from wordloom.pointer import PointerTarget, PointerText
from wordloom.providers import ApiError
from wordloom.ui import MainWindow
from wordloom.ui_lookup import popup_position
from tests.test_network import Connection, Response, json_result


class Backend:
    available=True
    reason=''
    failure=None
    def warmup(self): pass
    def capture_target(self): return PointerTarget(20,30,101,202,303)
    def is_current(self,target): return True
    def read(self,target,token,use_ocr,progress):
        token.check()
        if self.failure: raise self.failure
        return PointerText('serendipity','a moment of serendipity','ocr',(10,20,80,20))
    def cancel(self): pass
    def close(self): pass


class PointerUITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp=TemporaryDirectory()
        self.path=Path(self.temp.name)
        self.library=Library(self.path/'library.sqlite3')
        self.profile=Profile(base_url='http://127.0.0.1:8765/v1',model='test')
        with patch('wordloom.ui.create_hotkeys',return_value=UnsupportedHotkeys()), patch('wordloom.ui_lookup.create_pointer',return_value=Backend()):
            self.window=MainWindow(ConfigStore(self.path),Settings([self.profile],self.profile.id),self.library,Credentials())
        self.controller=self.window.pointer_lookup
        self.popup=self.controller.popup
        self.window.hide()

    def tearDown(self):
        self.window.close()
        self.app.processEvents()
        self.library.close()
        self.temp.cleanup()

    def until(self,condition,seconds=3):
        from PySide6.QtTest import QTest
        deadline=time.monotonic()+seconds
        while not condition() and time.monotonic()<deadline: QTest.qWait(10)
        self.assertTrue(condition())

    def test_pointer_no_selection_popup_translation_context_save_review(self):
        self.window.input.setPlainText('old input should remain untouched')
        self.app.clipboard().setText('old clipboard')
        with patch('wordloom.network.http.client.HTTPConnection',return_value=Connection(Response(json_result('意外的好运')))):
            self.window.lookup_requested()
            self.until(lambda:self.controller.completion is not None)
        self.assertFalse(self.window.isVisible())
        self.assertTrue(self.popup.isVisible())
        self.assertEqual(self.window.input.toPlainText(),'old input should remain untouched')
        self.assertEqual(self.app.clipboard().text(),'old clipboard')
        self.assertEqual(self.popup.word.text(),'serendipity')
        self.assertIn('moment',self.popup.context.toPlainText())
        self.assertIn('本机 OCR',self.popup.source.text())
        self.popup.save_button.click()
        entry=self.library.search()[0]
        self.assertEqual(entry.context,'a moment of serendipity')
        self.assertEqual(entry.meaning,'意外的好运')
        self.assertEqual(len(self.library.due_entries()),1)
        self.library.review(entry.id,'good',expected_revision=entry.revision)
        self.assertEqual(self.library.get(entry.id).repetitions,1)

    def test_failure_popup_with_manual_workbench_entry_no_model_request(self):
        self.controller.backend.failure=ApiError('pointer_ocr_missing','本机 OCR 语言不可用')
        with patch('wordloom.ui_lookup.Client') as client:
            self.window.lookup_requested()
            self.until(lambda:self.controller.capture_job is not None and not self.controller.capture_job.active)
            self.assertTrue(self.popup.isVisible())
            self.assertIn('语言不可用',self.popup.status.text())
            self.assertFalse(self.popup.save_button.isEnabled())
            self.popup.main_button.click()
            self.assertTrue(self.window.isVisible())
            self.assertTrue(self.window.paste_button.isEnabled())
            client.assert_not_called()

    def test_editing_requires_retranslate_and_close_cancels_model(self):
        with patch('wordloom.network.http.client.HTTPConnection',return_value=Connection(Response(json_result('first')))):
            self.controller.trigger()
            self.until(lambda:self.controller.completion is not None)
        self.popup.context.setPlainText('corrected surrounding sentence')
        self.assertIsNone(self.controller.completion)
        self.assertFalse(self.popup.save_button.isEnabled())
        connection=Connection(Response())
        connection.response.read1=lambda size:(connection.shutdown_event.wait(2),b'')[1]
        with patch('wordloom.network.http.client.HTTPConnection',return_value=connection):
            self.popup.translate_button.click()
            QTest.keyClick(self.popup, Qt.Key.Key_Escape)
            self.controller.model_job.thread.join(2)
            self.app.processEvents()
        self.assertFalse(self.controller.model_job.active)
        self.assertFalse(self.popup.isVisible())
        self.assertEqual(self.library.search(),[])

    def test_popup_stays_inside_negative_monitor_bounds(self):
        bounds=QRect(-1920,0,1920,1080)
        for point in (QPoint(-1919,1),QPoint(-1,1079),QPoint(-1000,600)):
            position=popup_position(point,QSize(440,520),bounds)
            self.assertTrue(bounds.contains(QRect(position,QSize(440,520))))
