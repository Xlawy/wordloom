"""Windows point-text and local OCR via reusable, killable helper processes."""
import ctypes
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
from uuid import uuid4
from ..pointer import PointerTarget, parse_pointer, pointer_error
from ..providers import ApiError


class PipeHelper:
    """One request at a time; queues belong to process generations, never replayed."""
    def __init__(self, mode, launch=None):
        self.mode = mode
        self.launch = launch or self._launch
        self.state_lock = threading.Lock()
        self.request_lock = threading.Lock()
        self.process = None
        self.output = None

    def _launch(self):
        executable = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        script = Path(__file__).parents[1] / 'resources' / 'pointer_worker.ps1'
        return subprocess.Popen([str(executable), '-NoProfile', '-NonInteractive', '-MTA', '-ExecutionPolicy', 'Bypass',
                                 '-File', str(script), '-Mode', self.mode],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def start(self):
        with self.state_lock:
            if self.process is not None and self.process.poll() is None:
                return self.process, self.output
            try:
                proc = self.launch()
            except OSError:
                pointer_error('helper')
            output = queue.Queue(maxsize=4)
            self.process, self.output = proc, output
            def read():
                try:
                    while True:
                        line = proc.stdout.readline(65537)
                        if not line or len(line) > 65536:
                            output.put_nowait(None)
                            break
                        output.put_nowait(line)
                except (OSError, ValueError, queue.Full):
                    pass
                finally:
                    proc.stdout.close()
            threading.Thread(target=read, name='wordloom-pointer-pipe', daemon=True).start()
            return proc, output

    def discard(self, expected=None):
        with self.state_lock:
            proc = self.process
            if proc is None or (expected is not None and proc is not expected):
                return
            self.process = self.output = None
        try:
            if proc.poll() is None:
                proc.kill()
        except OSError:
            pass
        try:
            proc.stdin.close()
        except OSError:
            pass
        def reap():
            try:
                proc.wait(timeout=2)
            except (OSError, subprocess.TimeoutExpired):
                pass
        threading.Thread(target=reap, name='wordloom-pointer-reap', daemon=True).start()

    def request(self, data, token, timeout, still_current):
        with self.request_lock:
            token.check()
            proc, output = self.start()
            try:
                token.check()
                if not still_current():
                    pointer_error('changed')
                request_id = uuid4().hex
                proc.stdin.write((json.dumps({**data, 'id': request_id}) + '\n').encode('utf-8'))
                proc.stdin.flush()
                deadline = time.monotonic() + timeout
                while True:
                    token.check()
                    if not still_current():
                        pointer_error('changed')
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        pointer_error('timeout')
                    try:
                        value = output.get(timeout=min(.05, remaining))
                    except queue.Empty:
                        continue
                    if value is None:
                        pointer_error('helper')
                    try:
                        envelope = json.loads(value)
                    except (ValueError, UnicodeError):
                        pointer_error('helper')
                    if not isinstance(envelope, dict) or envelope.get('id') != request_id:
                        pointer_error('helper')
                    token.check()
                    return value
            except (OSError, ValueError):
                self.discard(proc)
                token.check()
                pointer_error('helper')
            except Exception:
                self.discard(proc)
                raise


class WindowsPointerFocus:
    def __init__(self):
        from ctypes import wintypes as w
        self.w = w
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.api.GetPhysicalCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
        self.api.GetPhysicalCursorPos.restype = w.BOOL
        self.api.WindowFromPoint.argtypes = [w.POINT]
        self.api.WindowFromPoint.restype = w.HWND
        self.api.GetAncestor.argtypes = [w.HWND, w.UINT]
        self.api.GetAncestor.restype = w.HWND
        self.api.GetForegroundWindow.argtypes = []
        self.api.GetForegroundWindow.restype = w.HWND
        self.api.GetWindowThreadProcessId.argtypes = [w.HWND, ctypes.POINTER(w.DWORD)]
        self.api.GetWindowThreadProcessId.restype = w.DWORD
        self.api.IsWindow.argtypes = [w.HWND]
        self.api.IsWindow.restype = w.BOOL

    def capture(self):
        point = self.w.POINT()
        if not self.api.GetPhysicalCursorPos(ctypes.byref(point)):
            pointer_error('helper')
        window = self.api.WindowFromPoint(point)
        root = self.api.GetAncestor(window, 2) or window
        pid = self.w.DWORD()
        self.api.GetWindowThreadProcessId(root, ctypes.byref(pid))
        if not root or not pid.value or pid.value == os.getpid():
            pointer_error('empty')
        return PointerTarget(point.x, point.y, int(root), pid.value, int(self.api.GetForegroundWindow() or 0))

    def matches(self, target):
        pid = self.w.DWORD()
        self.api.GetWindowThreadProcessId(target.window, ctypes.byref(pid))
        return (bool(self.api.IsWindow(target.window)) and pid.value == target.pid
                and int(self.api.GetForegroundWindow() or 0) == target.foreground)


class UnsupportedPointer:
    available = False
    reason = '此平台尚未实现指针取词和本机 OCR。macOS 适配与原生验收待完成。'
    def close(self): pass
    def cancel(self): pass
    def warmup(self): pass


class WindowsPointer:
    available = True
    reason = ''
    def __init__(self, focus=None, uia=None, ocr=None):
        self.focus = focus or WindowsPointerFocus()
        self.uia, self.ocr = uia or PipeHelper('uia'), ocr or PipeHelper('ocr')
        self.closed = threading.Event()

    def warmup(self):
        def run():
            for helper in (self.uia, self.ocr):
                if self.closed.is_set():
                    return
                try:
                    proc, output = helper.start()
                    if self.closed.is_set():
                        helper.discard(proc)
                except ApiError:
                    pass
        threading.Thread(target=run, name='wordloom-pointer-warmup', daemon=True).start()

    def capture_target(self):
        return self.focus.capture()

    def is_current(self, target):
        return not self.closed.is_set() and self.focus.matches(target)

    def read(self, target, token, use_ocr=True, progress=lambda value: None):
        data = {'x': target.x, 'y': target.y, 'window': target.window, 'foreground': target.foreground}
        valid = lambda: self.is_current(target)
        try:
            progress('正在读取鼠标下的单词与上下文…')
            result = parse_pointer(self.uia.request(data, token, 1.5, valid), target)
            token.check()
            return result
        except ApiError as exc:
            if exc.code in ('cancelled', 'timeout', 'pointer_protected', 'pointer_changed'):
                raise
            if not use_ocr:
                raise
        token.check()
        if not valid():
            pointer_error('changed')
        progress('文本接口不可用，正在本机识别指针附近画面…')
        result = parse_pointer(self.ocr.request(data, token, 8, valid), target)
        token.check()
        if not valid():
            pointer_error('changed')
        return result

    def cancel(self):
        self.uia.discard()
        self.ocr.discard()

    def close(self):
        self.closed.set()
        self.cancel()


def create_pointer():
    return WindowsPointer() if sys.platform == 'win32' else UnsupportedPointer()
