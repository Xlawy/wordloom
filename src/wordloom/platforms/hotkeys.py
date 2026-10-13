"""Windows RegisterHotKey adapter. No keyboard hook or background key logging."""
import sys
from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication
from ..desktop import DesktopError


class UnsupportedHotkeys:
    available = False
    reason = '此平台尚未实现全局快捷键；macOS 原生适配与验收待完成。'

    def close(self):
        pass


class WinAPI:
    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.ctypes = ctypes
        self.user32 = ctypes.WinDLL('user32', use_last_error=True)
        self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        self.user32.RegisterHotKey.restype = wintypes.BOOL
        self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        self.user32.UnregisterHotKey.restype = wintypes.BOOL
        self.user32.SetForegroundWindow.argtypes = [wintypes.HWND]
        self.user32.SetForegroundWindow.restype = wintypes.BOOL

    def register(self, ident, modifiers, key):
        if not self.user32.RegisterHotKey(None, ident, modifiers | 0x4000, key):
            error = self.ctypes.get_last_error()
            detail = '已被其他程序占用' if error == 1409 else '系统保留或注册失败'
            raise DesktopError(f'快捷键{detail}（Windows 错误 {error}）。请选择其他组合；原快捷键保留。')

    def unregister(self, ident):
        self.user32.UnregisterHotKey(None, ident)

    def foreground(self, handle):
        self.user32.SetForegroundWindow(handle)


class WindowsHotkeys(QAbstractNativeEventFilter):
    available = True
    reason = ''

    def __init__(self, api=None):
        super().__init__()
        self.api = api or WinAPI()
        self.callbacks = {}
        self.app = QCoreApplication.instance()
        self.app.installNativeEventFilter(self)

    def register(self, ident, modifiers, key, callback):
        self.api.register(ident, modifiers, key)
        self.callbacks[ident] = callback

    def unregister(self, ident):
        self.callbacks.pop(ident, None)
        self.api.unregister(ident)

    def dispatch(self, message, ident):
        if message == 0x0312 and ident in self.callbacks:
            self.callbacks[ident]()
            return True
        return False

    def nativeEventFilter(self, event_type, message):
        if sys.platform == 'win32' and bytes(event_type) in (b'windows_generic_MSG', b'windows_dispatcher_MSG'):
            import ctypes
            from ctypes import wintypes
            msg = ctypes.cast(int(message), ctypes.POINTER(wintypes.MSG)).contents
            if self.dispatch(msg.message, msg.wParam):
                return True, 0
        return False, 0

    def close(self):
        for ident in list(self.callbacks):
            self.unregister(ident)
        self.app.removeNativeEventFilter(self)


def create_hotkeys():
    return WindowsHotkeys() if sys.platform == 'win32' else UnsupportedHotkeys()
