from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="语笺 WordLoom — 本地词库与自定义模型")
    parser.add_argument("--data-dir", type=Path, help="独立数据目录（不影响其他应用）")
    parser.add_argument("--smoke-test", action="store_true", help="启动窗口后自动退出，供环境检查")
    args = parser.parse_args()
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtCore import QLockFile, QTimer
    except ImportError as exc:
        import importlib.util
        if importlib.util.find_spec("PySide6") is None:
            print('缺少 PySide6。请在项目虚拟环境中执行：python -m pip install -e .', file=sys.stderr)
        else:
            print(f'Qt 图形运行环境不可用：{exc}\nPython 包已安装；请检查系统图形库（Linux 包括 libEGL.so.1）。', file=sys.stderr)
        return 2
    from .config import ConfigStore, data_directory
    from .library import Library
    from .platforms.credentials import Credentials
    from .ui import MainWindow
    from .theme import Theme
    app = QApplication(sys.argv[:1])
    app.setApplicationName("WordLoom")
    app.setOrganizationName("WordLoom")
    theme = Theme(app)
    directory = (args.data_dir or data_directory()).resolve()
    library = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(directory / "application.lock"))
        if not lock.tryLock(0):
            QMessageBox.information(None, "语笺已打开", "此数据目录正在使用中，请切换到已有窗口，或使用其他 --data-dir。")
            return 1
        store = ConfigStore(directory)
        settings = store.load()
        library = Library(directory / "library.sqlite3")
        window = MainWindow(store, settings, library, Credentials.native())
        window.show()
        if args.smoke_test:
            QTimer.singleShot(500, window.close)
        result = app.exec()
        lock.unlock()
        return result
    except Exception:
        QMessageBox.critical(None, "无法打开语笺", "配置或词库无法读取。原数据已保留，请检查数据目录权限、文件格式及应用版本。")
        return 1
    finally:
        if library:
            library.close()


if __name__ == "__main__":
    raise SystemExit(main())
