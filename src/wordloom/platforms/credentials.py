from __future__ import annotations

import sys
from typing import Protocol


class CredentialError(RuntimeError):
    pass


class Backend(Protocol):
    def get_password(self, service: str, account: str) -> str | None: ...
    def set_password(self, service: str, account: str, value: str) -> None: ...
    def delete_password(self, service: str, account: str) -> None: ...


class Credentials:
    SERVICE = "org.wordloom.desktop.api"

    def __init__(self, backend: Backend | None = None):
        self.backend = backend
        self._session: dict[str, str] = {}

    @classmethod
    def native(cls) -> Credentials:
        # Instantiate only known native backends, never user-selected plaintext plugins.
        try:
            if sys.platform == "win32":
                from keyring.backends.Windows import WinVaultKeyring
                return cls(WinVaultKeyring())
            if sys.platform == "darwin":
                from keyring.backends.macOS import Keyring
                return cls(Keyring())
        except ImportError:
            pass
        return cls()

    @property
    def available(self) -> bool:
        return self.backend is not None

    def get(self, account: str) -> str:
        if account in self._session:
            return self._session[account]
        if self.backend is None:
            return ""
        try:
            return self.backend.get_password(self.SERVICE, account) or ""
        except Exception:
            raise CredentialError("系统凭据库读取失败或被锁定。请解锁后重试，或明确设置本次会话密钥。") from None

    def set(self, account: str, value: str, *, session_only: bool = False) -> None:
        if len(value) > 4096 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise CredentialError("API Key 不能包含空白、换行或非 ASCII 字符。")
        if session_only:
            self._session[account] = value
            return
        if self.backend is None:
            raise CredentialError("当前系统凭据库不可用。请选择“仅本次会话”，密钥不会写入磁盘。")
        try:
            if value:
                self.backend.set_password(self.SERVICE, account, value)
            elif self.backend.get_password(self.SERVICE, account) is not None:
                self.backend.delete_password(self.SERVICE, account)
        except Exception:
            raise CredentialError("系统凭据库保存失败；没有回退到明文文件。") from None
        self._session.pop(account, None)

    def delete(self, account: str) -> None:
        if self.backend is not None:
            try:
                if self.backend.get_password(self.SERVICE, account) is not None:
                    self.backend.delete_password(self.SERVICE, account)
            except Exception:
                raise CredentialError("系统凭据删除失败。请解锁系统凭据库后重试。") from None
        self._session.pop(account, None)

    def clear_session(self) -> None:
        self._session.clear()
