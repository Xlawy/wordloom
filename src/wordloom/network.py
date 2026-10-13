from __future__ import annotations

from dataclasses import dataclass
import http.client
import json
import socket
import ssl
import threading
from urllib.parse import urlsplit

from .config import Profile
from .providers import ApiError, SSEDecoder, adapter_for, parse_json


class Cancellation:
    def __init__(self):
        self.event = threading.Event()
        self.connection: http.client.HTTPConnection | None = None
        self.socket: socket.socket | None = None
        self.timed_out = False

    def cancel(self, *, timeout: bool = False):
        if self.event.is_set():
            return
        self.timed_out = timeout
        self.event.set()
        conn = self.connection
        if conn:
            active_socket = self.socket or conn.sock
            if active_socket:
                try:
                    active_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            conn.close()

    def check(self):
        if self.event.is_set():
            if self.timed_out:
                raise ApiError("timeout", "请求超时。可增加超时或稍后手动重试。")
            raise ApiError("cancelled", "已取消请求。")


@dataclass(frozen=True)
class Completion:
    text: str
    finish_reason: str | None


def redact(text: str, secret: str, *, partial: bool = False) -> str:
    if not secret:
        return text
    value = text.replace(secret, "[密钥已隐藏]")
    if partial:
        # Do not display a credential split across stream chunks.
        for n in range(min(len(secret) - 1, len(value)), 0, -1):
            if value.endswith(secret[:n]):
                return value[:-n]
    return value


class Client:
    """Blocking transport for worker threads; no UI or automatic retries."""
    MAX_BYTES = 4_000_000

    def complete(self, profile: Profile, key: str, text: str, context: str = "", mode: str = "translate",
                 *, cancellation: Cancellation | None = None, on_text=lambda text: None,
                 image: bytes | None = None) -> Completion:
        adapter = adapter_for(profile)
        body = adapter.payload(profile, text, context, mode, image)
        return self._request(profile, key, "chat/completions", body, cancellation or Cancellation(), on_text)

    def models(self, profile: Profile, key: str, *, cancellation: Cancellation | None = None) -> list[str]:
        profile.validate(require_model=False)
        data = self._request(profile, key, "models", None, cancellation or Cancellation(), lambda value: None)
        names = adapter_for(profile).models(data)
        return [name for name in names if not key or key not in name][:500]

    def _request(self, profile, key, endpoint, body, cancel, on_text):
        if any(ord(c) < 33 or ord(c) > 126 for c in key) or len(key) > 4096:
            raise ApiError("configuration", "API Key 格式无效。")
        cancel.check()
        u = urlsplit(profile.base_url + "/" + endpoint)
        headers = {"Content-Type": "application/json", "Accept": "text/event-stream, application/json", "User-Agent": "WordLoom/0.1"}
        if key:
            headers["Authorization"] = "Bearer " + key
        conn = (http.client.HTTPSConnection(u.hostname, u.port, timeout=profile.timeout, context=ssl.create_default_context())
                if u.scheme == "https" else http.client.HTTPConnection(u.hostname, u.port, timeout=profile.timeout))
        cancel.connection = conn
        timer = threading.Timer(profile.timeout, lambda: cancel.cancel(timeout=True))
        timer.daemon = True
        timer.start()
        try:
            cancel.check()
            conn.connect()
            cancel.socket = conn.sock
            cancel.check()
            conn.request("POST" if body is not None else "GET", u.path, body=None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8"), headers=headers)
            cancel.check()
            response = conn.getresponse()
            cancel.check()
            status = response.status
            if status != 200:
                self._raise_status(status, response.getheader("Retry-After", ""))
            streaming = "text/event-stream" in response.getheader("Content-Type", "").lower()
            decoder = SSEDecoder()
            raw = bytearray()
            total = 0
            text = ""
            reason = None
            ended = False
            adapter = adapter_for(profile)
            while True:
                cancel.check()
                chunk = response.read1(8192)
                cancel.check()
                if not chunk:
                    break
                total += len(chunk)
                if total > self.MAX_BYTES:
                    raise ApiError("response", "响应超过 4 MB 限制。")
                if streaming:
                    for event in decoder.feed(chunk):
                        if event.strip() == "[DONE]":
                            ended = True
                            break
                        content, finish = adapter.content(parse_json(event), streaming=True)
                        text += content
                        if finish is not None:
                            reason = finish
                        if content:
                            on_text(redact(text, key, partial=True))
                    if ended:
                        break
                else:
                    raw.extend(chunk)
            cancel.check()
            if body is None:
                if streaming:
                    raise ApiError("response", "模型列表接口意外返回流式内容。")
                return parse_json(raw)
            if streaming:
                if decoder.buffer.strip() or decoder.lines or (not ended and reason is None):
                    raise ApiError("interrupted", "流式连接在完成前中断；未将部分结果标为完成。请手动重试。")
            else:
                text, reason = adapter.content(parse_json(raw), streaming=False)
            if not text.strip():
                raise ApiError("response", "模型返回空内容或仅返回工具调用；请选择支持文本输出的模型。")
            text = redact(text, key)
            on_text(text)
            return Completion(text, reason)
        except ApiError:
            raise
        except (socket.timeout, TimeoutError):
            cancel.check()
            raise ApiError("timeout", "请求超时。可增加超时或稍后手动重试。") from None
        except ssl.SSLError:
            cancel.check()
            raise ApiError("tls", "TLS 证书验证或握手失败，请检查服务地址和系统证书。") from None
        except (OSError, http.client.HTTPException, ValueError):
            cancel.check()
            raise ApiError("network", "网络连接中断或无法连接。请检查地址、网络和服务状态后重试。") from None
        finally:
            timer.cancel()
            conn.close()
            cancel.connection = None
            cancel.socket = None

    @staticmethod
    def _raise_status(status: int, retry_after: str):
        if status in (401, 403):
            raise ApiError("auth", f"鉴权失败（HTTP {status}）。请检查 API Key 和模型访问权限。")
        if status == 429:
            delay = f"建议等待 {min(int(retry_after), 86400)} 秒。" if retry_after.isdigit() and len(retry_after) < 9 else "请稍后手动重试。"
            raise ApiError("rate_limit", "服务限流或额度不足（HTTP 429）。" + delay)
        if 300 <= status < 400:
            raise ApiError("redirect", "服务要求重定向，已停止以避免转发密钥。请直接填写最终 API 根地址。")
        if status in (400, 404, 405, 422):
            raise ApiError("compatibility", f"请求不兼容（HTTP {status}）。检查根路径、模型、协议；可关闭温度/长度或切换长度字段。模型列表不可用时请手动输入。")
        if status >= 500:
            raise ApiError("server", f"模型服务异常（HTTP {status}）。请稍后手动重试。")
        raise ApiError("http", f"请求失败（HTTP {status}）。请检查服务配置。")
