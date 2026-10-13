import json
import subprocess
import sys
import threading
import unittest
from wordloom.network import Cancellation
from wordloom.platforms.selection import WindowsSelection, decode_selection
from wordloom.providers import ApiError


class Focus:
    valid = True
    def capture(self):
        return (123, 456)
    def matches(self, target):
        return self.valid and target == (123, 456)


class SelectionTests(unittest.TestCase):
    def helper(self, code, timeout=2, focus=None):
        children = []
        def launch(args, **kwargs):
            # Exercise real pipes/process termination without reading the OS desktop.
            process = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            children.append(process)
            return process
        return WindowsSelection(focus or Focus(), launch, timeout), children

    def test_unicode_selection_and_failure_codes(self):
        self.assertEqual(decode_selection(json.dumps({'code':'ok','text':'中文 🌿'}).encode()), '中文 🌿')
        for code in ('empty', 'unsupported', 'protected', 'unavailable', 'focus_changed', 'too_long'):
            with self.subTest(code=code), self.assertRaises(ApiError) as error:
                decode_selection(json.dumps({'code':code,'text':''}).encode())
            self.assertEqual(error.exception.code, 'selection_' + code)
        for raw in (b'not json', b'[]', b'{"code":"ok","text":123}', b'{"code":"ok","text":""}'):
            with self.assertRaises(ApiError):
                decode_selection(raw)
        with self.assertRaises(ApiError):
            decode_selection(json.dumps({'code':'ok','text':'x'*20001}).encode())

    def test_real_helper_process_output_and_cleanup(self):
        backend, children = self.helper('print(\'{"code":"ok","text":"selected-text"}\')')
        self.assertEqual(backend.read((123,456), Cancellation()), 'selected-text')
        self.assertIsNotNone(children[0].poll())
        self.assertIsNone(backend.process)

    def test_timeout_kills_real_helper(self):
        backend, children = self.helper('import time; time.sleep(30)', timeout=.1)
        with self.assertRaises(ApiError) as error:
            backend.read((123,456), Cancellation())
        self.assertEqual(error.exception.code, 'selection_timeout')
        self.assertIsNotNone(children[0].poll())

    def test_cancel_kills_real_helper_and_suppresses_output(self):
        backend, children = self.helper('import time; time.sleep(30)')
        token = Cancellation()
        timer = threading.Timer(.1, token.cancel)
        timer.start()
        try:
            with self.assertRaises(ApiError) as error:
                backend.read((123,456), token)
            self.assertEqual(error.exception.code, 'cancelled')
            self.assertIsNotNone(children[0].poll())
        finally:
            timer.cancel()

    def test_changed_focus_does_not_launch_helper(self):
        focus = Focus()
        focus.valid = False
        backend, children = self.helper('print("unexpected")', focus=focus)
        with self.assertRaises(ApiError) as error:
            backend.read((123,456), Cancellation())
        self.assertEqual(error.exception.code, 'selection_focus_changed')
        self.assertEqual(children, [])

    def test_changed_focus_during_read_kills_helper(self):
        focus = Focus()
        backend, children = self.helper('import time; time.sleep(30)', focus=focus)
        timer = threading.Timer(.1, lambda: setattr(focus, 'valid', False))
        timer.start()
        try:
            with self.assertRaises(ApiError) as error:
                backend.read((123,456), Cancellation())
            self.assertEqual(error.exception.code, 'selection_focus_changed')
            self.assertIsNotNone(children[0].poll())
        finally:
            timer.cancel()
