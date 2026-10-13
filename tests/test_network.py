from dataclasses import replace
import json
import socket
import ssl
import threading
import time
import unittest
from unittest.mock import patch

from wordloom.config import Profile
from wordloom.network import Cancellation, Client, redact
from wordloom.providers import ApiError, OpenAIChat, SSEDecoder


def json_result(text="你好", reason="stop"):
    return json.dumps({"choices": [{"message": {"content": text}, "finish_reason": reason}]}, ensure_ascii=False).encode()


def event(text="", reason=None):
    return ("data: " + json.dumps({"choices": [{"delta": {"content": text}, "finish_reason": reason}]}, ensure_ascii=False) + "\r\n\r\n").encode()


class Response:
    def __init__(self, data=b"", *, status=200, mime="application/json", chunks=None, headers=None):
        self.status = status
        self.headers = {"Content-Type": mime, **(headers or {})}
        self.chunks = list(chunks) if chunks is not None else [data]

    def getheader(self, name, default=""):
        return self.headers.get(name, default)

    def read1(self, size):
        return self.chunks.pop(0) if self.chunks else b""


class Connection:
    """In-memory HTTP boundary: real Client code builds/parses every request."""
    def __init__(self, response):
        self.response = response
        self.sock = self
        self.closed = False
        self.requests = []
        self.shutdown_event = threading.Event()

    def connect(self):
        pass

    def request(self, method, path, body=None, headers=None):
        self.requests.append((method, path, body, headers))

    def getresponse(self):
        return self.response

    def shutdown(self, how):
        self.shutdown_event.set()

    def close(self):
        self.closed = True


class NetworkTests(unittest.TestCase):
    def setUp(self):
        self.profile = Profile(base_url="http://127.0.0.1:8123/v1", model="user-model")
        self.client = Client()

    def run_request(self, response, **kwargs):
        connection = Connection(response)
        with patch("wordloom.network.http.client.HTTPConnection", return_value=connection):
            result = self.client.complete(self.profile, "not-a-real-key", "hello", "in a greeting", **kwargs)
        self.assertTrue(connection.closed)
        return result, connection

    def test_request_parameters_and_nonstream_fallback(self):
        result, c = self.run_request(Response(json_result()))
        method, path, body, headers = c.requests[0]
        payload = json.loads(body)
        self.assertEqual((method, path), ("POST", "/v1/chat/completions"))
        self.assertEqual(payload["model"], "user-model")
        self.assertIn("hello", payload["messages"][1]["content"])
        self.assertIn("in a greeting", payload["messages"][1]["content"])
        self.assertEqual(headers["Authorization"], "Bearer not-a-real-key")
        self.assertEqual(result.text, "你好")
        self.assertEqual(len(c.requests), 1)

    def test_optional_model_parameters(self):
        p = replace(self.profile, temperature=None, max_tokens=None)
        body = OpenAIChat().payload(p, "hello", "", "explain")
        self.assertNotIn("temperature", body)
        self.assertNotIn("max_tokens", body)
        p = replace(p, max_tokens=600, token_parameter="max_completion_tokens")
        self.assertEqual(OpenAIChat().payload(p, "hello", "", "examples")["max_completion_tokens"], 600)

    def test_fragmented_utf8_sse(self):
        raw = b": heartbeat\r\n\r\n" + event("你") + event("好") + event("", "stop") + b"data: [DONE]\r\n\r\n"
        partial = []
        result, _ = self.run_request(Response(mime="text/event-stream", chunks=[bytes([b]) for b in raw]), on_text=partial.append)
        self.assertEqual(result.text, "你好")
        self.assertIn("你", partial)
        self.assertEqual(result.finish_reason, "stop")

    def test_usage_only_sse_and_missing_done_with_finish(self):
        raw = event("text") + event("", "stop") + b'data: {"choices":[],"usage":{"total_tokens":5}}\n\n'
        result, _ = self.run_request(Response(raw, mime="text/event-stream"))
        self.assertEqual(result.text, "text")

    def test_truncated_stream_does_not_succeed(self):
        for raw in [event("half"), event("half") + b'data: {"choices"']:
            with self.subTest(raw=raw), self.assertRaises(ApiError) as cm:
                self.run_request(Response(raw, mime="text/event-stream"))
            self.assertEqual(cm.exception.code, "interrupted")

    def test_invalid_empty_and_refusal(self):
        for raw, code in [(b"<html>oops</html>", "response"), (b"{}", "response"), (json_result(""), "response"), (json_result("blocked", "content_filter"), "refusal"), (b'{"error":{"message":"secret"}}', "response")]:
            with self.subTest(raw=raw), self.assertRaises(ApiError) as cm:
                self.run_request(Response(raw))
            self.assertEqual(cm.exception.code, code)
            self.assertNotIn("secret", str(cm.exception))

    def test_http_errors_no_body_echo_no_retries(self):
        for status, code in [(401, "auth"), (403, "auth"), (429, "rate_limit"), (500, "server"), (404, "compatibility"), (422, "compatibility"), (302, "redirect")]:
            c = Connection(Response(b"not-a-real-key server echo", status=status, headers={"Retry-After": "3", "Location": "https://elsewhere.invalid/"}))
            with self.subTest(status=status), patch("wordloom.network.http.client.HTTPConnection", return_value=c), self.assertRaises(ApiError) as cm:
                self.client.complete(self.profile, "not-a-real-key", "hello")
            self.assertEqual(cm.exception.code, code)
            self.assertNotIn("not-a-real-key", str(cm.exception))
            self.assertEqual(len(c.requests), 1)

    def test_cancel_before_request_sends_nothing(self):
        token = Cancellation()
        token.cancel()
        with patch("wordloom.network.http.client.HTTPConnection") as connection, self.assertRaises(ApiError) as cm:
            self.client.complete(self.profile, "", "hello", cancellation=token)
        self.assertEqual(cm.exception.code, "cancelled")
        connection.assert_not_called()

    def test_cancel_midstream_closes_transport(self):
        token = Cancellation()
        c = Connection(Response(chunks=[event("first"), event("second"), event("", "stop")], mime="text/event-stream"))
        with patch("wordloom.network.http.client.HTTPConnection", return_value=c), self.assertRaises(ApiError) as cm:
            self.client.complete(self.profile, "", "hello", cancellation=token, on_text=lambda text: token.cancel())
        self.assertEqual(cm.exception.code, "cancelled")
        self.assertTrue(c.shutdown_event.is_set())
        self.assertTrue(c.closed)

    def test_total_deadline_aborts_slow_response(self):
        c = Connection(Response())
        c.response.read1 = lambda size: (c.shutdown_event.wait(2), b"")[1]
        started = time.monotonic()
        with patch("wordloom.network.http.client.HTTPConnection", return_value=c), self.assertRaises(ApiError) as cm:
            self.client.complete(replace(self.profile, timeout=1), "", "hello")
        self.assertEqual(cm.exception.code, "timeout")
        self.assertLess(time.monotonic() - started, 1.8)

    def test_network_and_tls_errors_sanitized(self):
        for exc, code in [(socket.timeout("secret"), "timeout"), (OSError("secret"), "network"), (ssl.SSLError("secret"), "tls")]:
            c = Connection(Response())
            c.connect = lambda e=exc: (_ for _ in ()).throw(e)
            with patch("wordloom.network.http.client.HTTPConnection", return_value=c), self.assertRaises(ApiError) as cm:
                self.client.complete(self.profile, "", "hello")
            self.assertEqual(cm.exception.code, code)
            self.assertNotIn("secret", str(cm.exception))

    def test_response_limit(self):
        with patch.object(Client, "MAX_BYTES", 10), self.assertRaises(ApiError):
            self.run_request(Response(b"x" * 11))

    def test_secret_echo_redacted_including_stream_boundary(self):
        key = "not-a-real-key"
        partial = []
        raw = event("key: not-a-") + event("real-key") + event("", "stop") + b"data: [DONE]\n\n"
        result, _ = self.run_request(Response(raw, mime="text/event-stream"), on_text=partial.append)
        self.assertNotIn(key, result.text)
        self.assertNotIn("not-a-", "|".join(partial))
        self.assertIn("密钥已隐藏", result.text)

    def test_models_and_authless_request(self):
        c = Connection(Response(b'{"data":[{"id":"user-2"},{"id":"user-1"}]}'))
        with patch("wordloom.network.http.client.HTTPConnection", return_value=c):
            names = self.client.models(replace(self.profile, model=""), "")
        self.assertEqual(names, ["user-1", "user-2"])
        self.assertEqual(c.requests[0][0:2], ("GET", "/v1/models"))
        self.assertNotIn("Authorization", c.requests[0][3])

    def test_ocr_explicit_capability_separate_profile(self):
        image = b"\x89PNG\r\n\x1a\nexample"
        with self.assertRaises(ApiError):
            OpenAIChat().payload(self.profile, "", "", "translate", image)
        ocr = replace(self.profile, purpose="ocr", vision=True)
        request = OpenAIChat().payload(ocr, "", "", "translate", image)
        self.assertEqual(request["messages"][1]["content"][1]["type"], "image_url")
        with self.assertRaises(ApiError):
            OpenAIChat().payload(ocr, "hello", "", "translate")
        with self.assertRaises(ApiError):
            OpenAIChat().payload(ocr, "", "", "translate", b"not-image")

    def test_length_finish_reported(self):
        result, _ = self.run_request(Response(json_result("partial", "length")))
        self.assertEqual(result.finish_reason, "length")

    def test_sse_multiline_heartbeat_and_bad_encoding(self):
        parser = SSEDecoder()
        self.assertEqual(parser.feed(b": hello\n\ndata: first\ndata: second\n\n"), ["first\nsecond"])
        with self.assertRaises(ApiError):
            parser.feed(b"data: \xff\n\n")

    def test_null_message_is_typed_response_error(self):
        with self.assertRaises(ApiError) as cm:
            self.run_request(Response(b'{"choices":[{"message":null}]}'))
        self.assertEqual(cm.exception.code, "response")
