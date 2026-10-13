"""Read selected text without clipboard writes or simulated keyboard input."""
from pathlib import Path
import base64
import json
import os
import subprocess
import sys
import threading
import time

from ..providers import ApiError

MESSAGES = {
    'empty': '没有读到选中文字。请先选中文字；也可手动复制后点击“粘贴剪贴板文本”。',
    'unsupported': '此控件未提供选区接口。请手动复制，再点击“粘贴剪贴板文本”。',
    'protected': '密码或受保护输入框不支持取词。请在普通文本中选择需要翻译的内容。',
    'focus_changed': '取词期间前台窗口已变化，本次未发送。请重新选择，或手动复制粘贴。',
    'too_long': '选区超过 20000 字符，请缩小选区后重试。',
    'unavailable': '无法访问目标选区；可能是权限限制、控件不支持或系统 UI Automation 不可用。请手动复制粘贴。',
    'helper_missing': 'Windows PowerShell 辅助程序不可用。请手动复制粘贴。',
    'timeout': '读取选区超时，已停止辅助进程。请手动复制粘贴。',
}


def fail(code):
    raise ApiError('selection_' + code, MESSAGES.get(code, MESSAGES['unavailable']))


def decode_selection(raw):
    if len(raw) > 256000:
        fail('too_long')
    try:
        value = json.loads(raw.decode('utf-8-sig'))
        if not isinstance(value, dict) or set(value) != {'code', 'text'}:
            raise ValueError()
        code, text = value['code'], value['text']
        if not isinstance(code, str) or not isinstance(text, str):
            raise ValueError()
    except (ValueError, UnicodeError):
        fail('unavailable')
    if code != 'ok':
        fail(code if code in MESSAGES else 'unavailable')
    if '\x00' in text:
        fail('unavailable')
    if len(text) > 20000:
        fail('too_long')
    if not text.strip():
        fail('empty')
    return text.strip()


class WindowsFocus:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.api.GetForegroundWindow.argtypes = []
        self.api.GetForegroundWindow.restype = wintypes.HWND
        self.api.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self.api.GetWindowThreadProcessId.restype = wintypes.DWORD

    def capture(self):
        from ctypes import wintypes
        handle = self.api.GetForegroundWindow()
        pid = wintypes.DWORD()
        if not handle or not self.api.GetWindowThreadProcessId(handle, self.ctypes.byref(pid)):
            fail('unavailable')
        if pid.value == os.getpid():
            fail('empty')
        return (int(handle), pid.value)

    def matches(self, target):
        try:
            return self.capture() == target
        except ApiError:
            return False


class UnsupportedSelection:
    available = False
    reason = '此平台尚未实现选区读取。请手动复制后使用粘贴入口；macOS 原生适配待完成。'
    def cancel(self):
        pass


class WindowsSelection:
    available = True
    reason = ''
    def __init__(self, focus=None, popen=subprocess.Popen, timeout=5):
        self.focus = focus or WindowsFocus()
        self.popen, self.timeout = popen, timeout
        self.lock = threading.Lock()
        self.process = None

    def capture_target(self):
        return self.focus.capture()

    def is_current(self, target):
        return self.focus.matches(target)

    def cancel(self):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                try:
                    self.process.kill()
                except OSError:
                    pass

    def read(self, target, token):
        token.check()
        if not self.is_current(target):
            fail('focus_changed')
        script = Path(__file__).parents[1] / 'resources' / 'read_selection.ps1'
        body = f'$ExpectedWindow = [Int64]{int(target[0])}\n' + script.read_text(encoding='utf-8')
        encoded = base64.b64encode(body.encode('utf-16-le')).decode('ascii')
        powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        proc = None
        try:
            with self.lock:
                token.check()
                proc = self.popen([str(powershell), '-NoProfile', '-NonInteractive', '-MTA', '-EncodedCommand', encoded],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.process = proc
            deadline = time.monotonic() + self.timeout
            while True:
                token.check()
                if not self.is_current(target):
                    fail('focus_changed')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    fail('timeout')
                try:
                    output, _ = proc.communicate(timeout=min(.05, remaining))
                    break
                except subprocess.TimeoutExpired:
                    continue
            token.check()
            if not self.is_current(target):
                fail('focus_changed')
            if proc.returncode:
                fail('unavailable')
            return decode_selection(output)
        except FileNotFoundError:
            fail('helper_missing')
        except OSError:
            token.check()
            fail('unavailable')
        finally:
            if proc is not None:
                if proc.poll() is None:
                    try:
                        proc.kill()
                    except OSError:
                        pass
                try:
                    proc.communicate(timeout=1)
                except (subprocess.TimeoutExpired, OSError):
                    pass
            with self.lock:
                if self.process is proc:
                    self.process = None


def create_selection():
    return WindowsSelection() if sys.platform == 'win32' else UnsupportedSelection()
