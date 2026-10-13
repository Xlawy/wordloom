"""Explicit native vault acceptance: disposable secret, separate reader process.

Never loads application profiles or existing credentials. No secret in argv/logs.
"""
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from uuid import uuid4

from wordloom.platforms.credentials import Credentials, CredentialError


def main():
    if sys.platform not in ("win32", "darwin"):
        print("ENVIRONMENT_RESTRICTED: native credential acceptance requires Windows or macOS")
        return 2
    vault = Credentials.native()
    if not vault.available:
        print("FAIL: native credential backend unavailable")
        return 1
    if len(sys.argv) == 2 and sys.argv[1] == "--read-child":
        account, expected = json.load(sys.stdin)
        return 0 if vault.get(account) == expected else 1
    account = "acceptance-" + uuid4().hex
    secret = secrets.token_urlsafe(32)
    status = 0
    try:
        vault.set(account, secret)
        env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--read-child"],
                               input=json.dumps([account, secret]), text=True, encoding="utf-8",
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=45)
        if child.returncode:
            print("FAIL: credential was not readable in a new process")
            status = 1
    except (CredentialError, OSError, subprocess.TimeoutExpired):
        print("FAIL: native credential write/read failed; no plaintext fallback")
        status = 1
    finally:
        try:
            vault.delete(account)
            if Credentials.native().get(account):
                raise CredentialError("delete failed")
        except CredentialError:
            print("FAIL: cleanup required in system vault: " + Credentials.SERVICE + " / " + account)
            status = 1
    if not status:
        print("PASS: native credential persisted across processes and was deleted")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
