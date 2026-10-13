import json
import subprocess
import sys
import threading
import unittest
from wordloom.network import Cancellation
from wordloom.pointer import PointerTarget, parse_pointer
from wordloom.platforms.pointer import PipeHelper, WindowsPointer
from wordloom.providers import ApiError

TARGET = PointerTarget(-100, 30, 101, 202, 303)


def result(source='uia', **kw):
    return json.dumps(dict(code='ok', word='serendipity', context='a moment of serendipity',
                           source=source, box=[-110, 20, 90, 20], **kw)).encode()


class Focus:
    valid = True
    def capture(self): return TARGET
    def matches(self, target): return self.valid and target == TARGET


class Helper:
    def __init__(self, response):
        self.response = response
        self.calls = 0
    def request(self, data, token, timeout, valid):
        self.calls += 1
        if isinstance(self.response, Exception): raise self.response
        return self.response
    def discard(self): pass


class PointerTests(unittest.TestCase):
    def test_safe_stage_errors_and_ocr_empty_distinctions(self):
        for code in ('ocr_error', 'ocr_missing', 'ocr_no_text', 'ocr_no_hit'):
            with self.assertRaises(ApiError) as raised:
                parse_pointer(json.dumps(dict(code=code, stage='hitbox')), TARGET)
            self.assertEqual(raised.exception.code, 'pointer_' + code)
            self.assertIn('hitbox', str(raised.exception))
        for stage in ('private screen content', ['capture'], None):
            with self.assertRaises(ApiError) as raised:
                parse_pointer(json.dumps(dict(code='ocr_error', stage=stage)), TARGET)
            self.assertNotIn('阶段', str(raised.exception))
            self.assertNotIn('private screen content', str(raised.exception))

    def test_word_context_and_physical_negative_coordinates(self):
        found = parse_pointer(result(), TARGET)
        self.assertEqual(found.word, 'serendipity')
        self.assertIn('serendipity', found.context)
        self.assertEqual(found.source, 'uia')
        with self.assertRaises(ApiError):
            parse_pointer(result(), PointerTarget(900,30,101,202,303))
        for change in ({'box':[0,0,-1,5]}, {'box':[True,2,3,4]}, {'word':'x'*129}, {'context':'x'*4001}):
            value = json.loads(result())
            value.update(change)
            with self.assertRaises(ApiError): parse_pointer(json.dumps(value), TARGET)

    def test_timeout_unsupported_and_bad_uia_use_local_ocr(self):
        for failure in (ApiError('pointer_timeout','timeout'), b'{"code":"unsupported"}', b'invalid'):
            uia, ocr = Helper(failure), Helper(result('ocr'))
            backend = WindowsPointer(Focus(), uia, ocr)
            self.assertEqual(backend.read(TARGET, Cancellation()).source, 'ocr')
            self.assertEqual((uia.calls, ocr.calls), (1,1))

    def test_protected_cancelled_changed_and_disabled_ocr_do_not_capture(self):
        for failure, enabled in ((ApiError('cancelled','cancelled'),True), (b'{"code":"protected"}',True),
                                 (ApiError('pointer_changed','changed'),True), (b'{"code":"unsupported"}',False)):
            uia, ocr = Helper(failure), Helper(result('ocr'))
            with self.assertRaises(ApiError): WindowsPointer(Focus(), uia, ocr).read(TARGET,Cancellation(),enabled)
            self.assertEqual(ocr.calls,0)

    def test_missing_ocr_returns_specific_message(self):
        backend = WindowsPointer(Focus(), Helper(b'{"code":"unsupported"}'), Helper(b'{"code":"ocr_missing"}'))
        with self.assertRaises(ApiError) as error: backend.read(TARGET,Cancellation())
        self.assertEqual(error.exception.code,'pointer_ocr_missing')
        self.assertIn('语言',str(error.exception))

    def pipe(self, delay=0, wrong_id=False):
        processes=[]
        code = '''import json,sys,time
for line in sys.stdin:
    value=json.loads(line)
    time.sleep(DELAY)
    print(json.dumps({'id': ID, 'code':'empty'}),flush=True)
'''.replace('DELAY',str(delay)).replace('ID', "'wrong-id'" if wrong_id else "value['id']")
        def launch():
            proc=subprocess.Popen([sys.executable,'-u','-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            processes.append(proc)
            return proc
        return PipeHelper('uia',launch),processes

    def test_real_pipe_reuses_process_and_matches_request_ids(self):
        helper,children=self.pipe()
        try:
            first=helper.request({'x':1},Cancellation(),2,lambda:True)
            second=helper.request({'x':2},Cancellation(),2,lambda:True)
            self.assertNotEqual(json.loads(first)['id'],json.loads(second)['id'])
            self.assertEqual(len(children),1)
        finally:
            helper.discard()
            children[0].wait(timeout=2)

    def test_real_pipe_timeout_kills_worker_and_next_request_restarts(self):
        helper,children=self.pipe(delay=.3)
        try:
            with self.assertRaises(ApiError): helper.request({},Cancellation(),.05,lambda:True)
            children[0].wait(timeout=2)
            self.assertIsNone(helper.process)
            helper.request({},Cancellation(),2,lambda:True)
            self.assertEqual(len(children),2)
        finally:
            helper.discard()
            for child in children: child.wait(timeout=2)

    def test_cancel_and_mismatched_id_cannot_replay_result(self):
        for wrong in (False,True):
            helper,children=self.pipe(delay=0 if wrong else .5, wrong_id=wrong)
            token=Cancellation()
            timer=threading.Timer(.1,token.cancel)
            if not wrong: timer.start()
            try:
                with self.assertRaises(ApiError): helper.request({},token,2,lambda:True)
                self.assertIsNone(helper.process)
            finally:
                timer.cancel()
                helper.discard()
                for child in children: child.wait(timeout=2)
