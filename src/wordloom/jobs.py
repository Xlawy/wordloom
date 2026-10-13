"""Qt bridge for cancellable worker I/O. Receivers always run on the GUI thread."""
from __future__ import annotations

import threading
from PySide6.QtCore import QObject, Signal, QTimer

from .network import Cancellation
from .providers import ApiError


class _Signals(QObject):
    progress = Signal(str)
    success = Signal(object)
    failure = Signal(str, str)


class Job(QObject):
    progress = Signal(str)
    success = Signal(object)
    failure = Signal(str, str)

    def __init__(self, function, timeout: float, parent=None):
        super().__init__(parent)
        self.token = Cancellation()
        self.active = True
        self.signals = _Signals()  # Retained by worker until it exits, even after window close.
        self.signals.progress.connect(self._progress)
        self.signals.success.connect(self._success)
        self.signals.failure.connect(self._failure)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._timeout)
        self.timer.start(int(timeout * 1000) + 100)
        signals, token = self.signals, self.token

        def run():
            try:
                result = function(token, signals.progress.emit)
                token.check()
                signals.success.emit(result)
            except ApiError as exc:
                signals.failure.emit(exc.code, str(exc))
            except Exception:
                # Never surface arbitrary exceptions containing URLs/headers/keys.
                signals.failure.emit("internal", "请求未完成，请检查配置后重试。")
        self.thread = threading.Thread(target=run, name="wordloom-request", daemon=True)

    def start(self):
        self.thread.start()

    def _progress(self, text):
        if self.active:
            self.progress.emit(text)

    def _success(self, result):
        if self.active:
            self.active = False
            self.timer.stop()
            self.success.emit(result)

    def _failure(self, code, message):
        if self.active:
            self.active = False
            self.timer.stop()
            self.failure.emit(code, message)

    def _timeout(self):
        self.token.cancel(timeout=True)
        self._failure("timeout", "请求超过总时限。请检查服务状态或增加超时。")

    def cancel(self):
        self.token.cancel()
        self._failure("cancelled", "已取消请求。")
