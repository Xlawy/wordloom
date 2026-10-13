"""Actual loopback HTTP tests. Permission-denied is explicitly an environment skip."""
from dataclasses import replace
import socket
import threading
import unittest

from scripts.mock_server import MockServer
from wordloom.config import Profile
from wordloom.network import Cancellation, Client
from wordloom.providers import ApiError


class LiveHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            with socket.socket() as probe:
                probe.bind(("127.0.0.1", 0))
        except PermissionError as exc:
            raise unittest.SkipTest(f"ENVIRONMENT_RESTRICTED: local sockets: {exc}") from None
        cls.server = MockServer()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(2)

    def setUp(self):
        self.profile = Profile(base_url=self.server.base_url, model="mock-stream")

    def test_stream_end_to_end(self):
        parts = []
        result = Client().complete(self.profile, "", "serendipity", "a lucky encounter", on_text=parts.append)
        self.assertIn("serendipity", result.text)
        self.assertIn("a lucky encounter", result.text)
        self.assertTrue(result.text.startswith("[MOCK"))
        self.assertGreater(len(parts), 2)

    def test_nonstream_and_models(self):
        result = Client().complete(replace(self.profile, model="mock-json"), "", "text")
        self.assertIn("text", result.text)
        self.assertIn("mock-stream", Client().models(self.profile, ""))

    def test_auth_and_rate(self):
        for model, expected in [("mock-auth", "auth"), ("mock-rate", "rate_limit")]:
            with self.subTest(model=model), self.assertRaises(ApiError) as cm:
                Client().complete(replace(self.profile, model=model), "test-only", "text")
            self.assertEqual(cm.exception.code, expected)

    def test_timeout(self):
        with self.assertRaises(ApiError) as cm:
            Client().complete(replace(self.profile, model="mock-timeout", timeout=1), "", "text")
        self.assertEqual(cm.exception.code, "timeout")

    def test_cancel_socket_stream(self):
        token = Cancellation()
        with self.assertRaises(ApiError) as cm:
            Client().complete(replace(self.profile, model="mock-slow-stream"), "", "text",
                              cancellation=token, on_text=lambda _: token.cancel())
        self.assertEqual(cm.exception.code, "cancelled")

    def test_broken_responses(self):
        for model, expected in [("mock-invalid", "response"), ("mock-interrupted", "interrupted")]:
            with self.subTest(model=model), self.assertRaises(ApiError) as cm:
                Client().complete(replace(self.profile, model=model), "", "text")
            self.assertEqual(cm.exception.code, expected)
