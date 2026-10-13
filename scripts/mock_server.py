"""Development fixture only, bound to loopback. Never contacts a model service."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time


MODELS = ["mock-stream", "mock-json", "mock-auth", "mock-rate", "mock-timeout",
          "mock-invalid", "mock-interrupted", "mock-slow-stream"]


class MockServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address=("127.0.0.1", 0)):
        super().__init__(address, Handler)
        self.received = []  # Test inputs only; never retain Authorization headers.

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server_address[1]}/v1"

    def handle_error(self, request, client_address):
        pass  # Deliberate client cancellation does not print request information.


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, status, data, mime="application/json", headers=None):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/v1/models":
            self.reply(200, {"data": [{"id": name} for name in MODELS]})
        else:
            self.reply(404, {"error": {"message": "unknown fixture path"}})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.reply(404, {})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length < 12_000_000:
            self.reply(400, {})
            return
        try:
            body = json.loads(self.rfile.read(length))
            model = body["model"]
            self.server.received.append(body)
            content = body["messages"][-1]["content"]
        except (ValueError, KeyError, TypeError):
            self.reply(400, {})
            return
        if model == "mock-auth":
            self.reply(401, {"error": {"message": "fixture authentication failure"}})
            return
        if model == "mock-rate":
            self.reply(429, {}, headers={"Retry-After": "2"})
            return
        if model == "mock-timeout":
            time.sleep(2.5)
        if model == "mock-invalid":
            self.reply(200, b"not JSON", "text/plain")
            return
        result = "[MOCK，仅测试，不是真实翻译]\n" + (content if isinstance(content, str) else "已收到图像测试请求")
        if model in ("mock-json", "mock-timeout") or not body.get("stream"):
            self.reply(200, {"choices": [{"message": {"content": result}, "finish_reason": "stop"}]})
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        try:
            for index in range(0, len(result), 6):
                event = {"choices": [{"delta": {"content": result[index:index + 6]}, "finish_reason": None}]}
                self.wfile.write(("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode())
                self.wfile.flush()
                if model == "mock-interrupted":
                    return
                time.sleep(0.2 if model == "mock-slow-stream" else 0.005)
            self.wfile.write(b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser(description="WordLoom 本地模拟服务，不是真实翻译")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = MockServer(("127.0.0.1", args.port))
    print("仅测试模拟服务：", server.base_url, "（无需 API Key）", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
