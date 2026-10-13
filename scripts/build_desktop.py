"""Build on the target OS. This does not sign or publish installers."""
import importlib.util
from pathlib import Path
import subprocess
import sys


def main():
    if sys.platform not in ("win32", "darwin"):
        print("Windows/macOS 产物须在对应系统构建；本脚本不从 WSL 伪装交叉构建。", file=sys.stderr)
        return 2
    if importlib.util.find_spec("PyInstaller") is None:
        print('请在此项目虚拟环境安装构建依赖：python -m pip install -e ".[build]"', file=sys.stderr)
        return 2
    root = Path(__file__).resolve().parents[1]
    args = [sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm", "--windowed",
            "--name", "WordLoom", "--collect-data", "wordloom", "--paths", str(root / "src"), "--distpath", str(root / "dist"),
            "--workpath", str(root / "build"), "--specpath", str(root / "build")]
    if sys.platform == "darwin":
        args += ["--osx-bundle-identifier", "org.wordloom.desktop", "--hidden-import", "keyring.backends.macOS"]
    else:
        args += ["--hidden-import", "keyring.backends.Windows"]
    args.append(str(root / "scripts/desktop_entry.py"))
    return subprocess.call(args, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
