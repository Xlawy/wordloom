"""Opt-in Windows registration/conflict/release probe. Does not inject key presses."""
import os
import subprocess
import sys
from pathlib import Path


def main():
    if sys.platform != 'win32':
        print('ENVIRONMENT_RESTRICTED: Windows native hotkey probe requires Windows')
        return 2
    from wordloom.platforms.hotkeys import WinAPI
    from wordloom.desktop import DesktopError
    api = WinAPI()
    ident = 0x5750
    if len(sys.argv) == 3 and sys.argv[1] == '--conflict-child':
        try:
            api.register(ident, 7, int(sys.argv[2]))
        except DesktopError:
            return 0 if api.ctypes.get_last_error() == 1409 else 1
        else:
            api.unregister(ident)
            return 1
    selected = None
    for key in (0x78, 0x79, 0x7A):  # Ctrl+Alt+Shift+F9/F10/F11, temporary only
        try:
            api.register(ident, 7, key)
            selected = key
            break
        except DesktopError:
            pass
    if selected is None:
        print('FAIL: no test shortcut available; choose a free combination and retry manually')
        return 1
    try:
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--conflict-child', str(selected)],
                                env=dict(os.environ, PYTHONUTF8='1'), capture_output=True, timeout=15)
        if result.returncode:
            print('FAIL: another process did not report expected hotkey conflict')
            return 1
    except (OSError, subprocess.TimeoutExpired):
        print('FAIL: conflict check child process failed')
        return 1
    finally:
        api.unregister(ident)
    try:
        api.register(ident, 7, selected)
        api.unregister(ident)
    except DesktopError:
        print('FAIL: hotkey was not reusable after release')
        return 1
    print('PASS: native registration, cross-process conflict and release; physical key delivery still requires manual acceptance')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
