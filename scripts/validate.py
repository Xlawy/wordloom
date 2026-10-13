"""Run isolated checks and retain exact status, including environment limitations."""
import argparse
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("validation"))
    parser.add_argument("--native-credentials", action="store_true", help="Probe native vault with a disposable test credential")
    parser.add_argument("--native-hotkeys", action="store_true", help="Probe Windows hotkey registration/conflict/release")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    args.output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    # Let imports work for both installed and source-tree execution.
    env["PYTHONPATH"] = str(root / "src") + os.pathsep + str(root)
    result = {"python": sys.executable, "platform": platform.platform(), "timestamp": datetime.now(timezone.utc).isoformat(), "packages": {}, "checks": []}
    for package in ("PySide6", "keyring"):
        try:
            result["packages"][package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result["packages"][package] = "not installed"
    with tempfile.TemporaryDirectory(prefix="wordloom-check-") as directory:
        cases = [("core-and-http", ["-m", "unittest", "discover", "-s", "tests", "-v"]),
                 ("ui", ["-m", "unittest", "discover", "-s", "checks", "-v"]),
                 ("startup", ["-m", "wordloom", "--smoke-test", "--data-dir", directory])]
        if args.native_credentials:
            cases.append(("native-credentials", ["scripts/check_credentials.py"]))
        if args.native_hotkeys:
            cases.append(("native-hotkeys", ["scripts/check_hotkeys.py"]))
        for name, command in cases:
            try:
                process = subprocess.run([sys.executable, *command], env=env, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", timeout=90)
                output, code = process.stdout, process.returncode
            except subprocess.TimeoutExpired:
                output, code = "CHECK_TIMEOUT: process did not finish within 90 seconds", 124
            (args.output / (name + ".log")).write_text(output, encoding="utf-8")
            restricted = any(marker in output for marker in ("ENVIRONMENT_RESTRICTED", "GUI_ENVIRONMENT_UNAVAILABLE", "Qt 图形运行环境不可用", "缺少 PySide6"))
            status = "environment_limited" if restricted else ("passed" if code == 0 else "failed")
            if "FAILED (" in output:
                status = "failed"
            result["checks"].append({"name": name, "command": [sys.executable, *command], "exit_code": code, "status": status, "log": name + ".log"})
            print(f"{name}: {status} (exit {code})", flush=True)
    (args.output / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if any(c["status"] == "failed" for c in result["checks"]):
        return 1
    return 2 if any(c["status"] == "environment_limited" for c in result["checks"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
