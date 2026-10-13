from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4


DEFAULT_PROMPTS = {
    "translate": "将下面的文本翻译成简体中文，结合上下文消除歧义。只输出翻译和必要的简短说明。",
    "explain": "你是语言学习助手。解释下面词语在给定上下文中的含义，给出词性、中文释义和常见用法。不要编造原文不存在的信息。",
    "examples": "为下面的词语生成三个自然的英文例句，每句附中文翻译，并说明常用搭配。",
}


class ConfigError(ValueError):
    pass


def data_directory() -> Path:
    override = os.environ.get("WORDLOOM_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "WordLoom"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/WordLoom"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "wordloom"


def normalize_url(value: str) -> str:
    if not isinstance(value, str) or any(ord(c) < 33 for c in value):
        raise ConfigError("API 根地址不能包含空格或控制字符。")
    try:
        u = urlsplit(value)
        _ = u.port
    except ValueError:
        raise ConfigError("API 地址格式无效。") from None
    if not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ConfigError("填写 API 根地址，不要含用户名、密码、查询参数或片段。")
    if u.scheme not in ("http", "https"):
        raise ConfigError("API 地址必须使用 HTTPS；本机服务可使用 HTTP。")
    if u.scheme == "http" and u.hostname.lower() not in ("localhost", "127.0.0.1", "::1"):
        raise ConfigError("远程 API 必须使用 HTTPS，避免发送明文密钥。")
    if u.path.rstrip("/").endswith(("/chat/completions", "/models")):
        raise ConfigError("请填写 API 根路径（例如 https://服务商/v1），不要填具体请求端点。")
    return urlunsplit((u.scheme, u.netloc.lower(), u.path.rstrip("/"), "", ""))


@dataclass
class Profile:
    id: str = field(default_factory=lambda: uuid4().hex)
    name: str = "新配置"
    purpose: str = "translation"
    protocol: str = "openai_chat"
    base_url: str = ""
    model: str = ""
    timeout: float = 45
    temperature: float | None = 0.3
    max_tokens: int | None = 2048
    token_parameter: str = "max_tokens"
    stream: bool = True
    vision: bool = False
    prompts: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PROMPTS))

    def validate(self, *, require_model: bool = True) -> None:
        if not isinstance(self.id, str) or len(self.id) != 32 or any(c not in "0123456789abcdef" for c in self.id):
            raise ConfigError("配置 ID 无效。")
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 100:
            raise ConfigError("请输入 1–100 字符的配置名称。")
        if self.purpose not in ("translation", "ocr") or self.protocol != "openai_chat":
            raise ConfigError("此版本只支持 OpenAI 兼容 Chat Completions 协议。")
        self.base_url = normalize_url(self.base_url.strip())
        if not isinstance(self.model, str) or len(self.model) > 256 or (require_model and not self.model.strip()):
            raise ConfigError("请输入模型名称；获取模型列表时可暂时留空。")
        if type(self.timeout) not in (int, float) or not math.isfinite(self.timeout) or not 1 <= self.timeout <= 600:
            raise ConfigError("超时必须在 1–600 秒之间。")
        if self.temperature is not None and (type(self.temperature) not in (int, float) or not math.isfinite(self.temperature) or not 0 <= self.temperature <= 2):
            raise ConfigError("温度必须在 0–2 之间，或关闭此参数。")
        if self.max_tokens is not None and (type(self.max_tokens) is not int or not 1 <= self.max_tokens <= 131072):
            raise ConfigError("输出长度必须在 1–131072 之间，或关闭此参数。")
        if self.token_parameter not in ("max_tokens", "max_completion_tokens"):
            raise ConfigError("不支持的输出长度参数。")
        if type(self.stream) is not bool or type(self.vision) is not bool:
            raise ConfigError("流式或图像能力设置无效。")
        if not isinstance(self.prompts, dict) or set(self.prompts) != set(DEFAULT_PROMPTS):
            raise ConfigError("翻译、释义、例句提示词必须完整。")
        if any(not isinstance(v, str) or not v.strip() or len(v) > 16000 for v in self.prompts.values()):
            raise ConfigError("提示词必须为 1–16000 字符。")

    @property
    def credential_id(self) -> str:
        origin = normalize_url(self.base_url) + "|" + self.purpose
        return self.id + ":" + hashlib.sha256(origin.encode()).hexdigest()[:24]


@dataclass
class Settings:
    profiles: list[Profile] = field(default_factory=list)
    active_translation: str | None = None
    active_ocr: str | None = None

    def active(self, purpose: str = "translation") -> Profile | None:
        ident = self.active_translation if purpose == "translation" else self.active_ocr
        return next((p for p in self.profiles if p.id == ident and p.purpose == purpose), None)

    def upsert(self, profile: Profile) -> None:
        profile.validate()
        self.profiles = [p for p in self.profiles if p.id != profile.id] + [profile]
        self.repair_active()

    def remove(self, ident: str) -> None:
        self.profiles = [p for p in self.profiles if p.id != ident]
        self.repair_active()

    def repair_active(self) -> None:
        for purpose in ("translation", "ocr"):
            if self.active(purpose) is None:
                first = next((p.id for p in self.profiles if p.purpose == purpose), None)
                setattr(self, "active_" + purpose, first)


class ConfigStore:
    def __init__(self, directory: Path):
        self.path = directory / "settings.json"

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            if self.path.stat().st_size > 2_000_000:
                raise ValueError()
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if data.get("schema") != 1 or set(data) != {"schema", "profiles", "active_translation", "active_ocr"}:
                raise ValueError()
            if not isinstance(data["profiles"], list) or len(data["profiles"]) > 100:
                raise ValueError()
            profiles = [Profile(**p) for p in data["profiles"]]
            for p in profiles:
                p.validate()
            if len({p.id for p in profiles}) != len(profiles):
                raise ValueError()
            settings = Settings(profiles, data["active_translation"], data["active_ocr"])
            settings.repair_active()
            return settings
        except (ValueError, TypeError, KeyError, AttributeError):
            raise ConfigError("配置文件无效或版本不支持。原文件已保留，请备份后修复 settings.json。") from None

    def save(self, settings: Settings) -> None:
        if len(settings.profiles) > 100:
            raise ConfigError("最多保存 100 个配置。")
        for p in settings.profiles:
            p.validate()
        settings.repair_active()
        data = {"schema": 1, **asdict(settings)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.path, json.dumps(data, ensure_ascii=False, indent=2))


def atomic_write(path: Path, text: str) -> None:
    fd, name = tempfile.mkstemp(prefix=".wordloom-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
