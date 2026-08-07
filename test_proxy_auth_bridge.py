from __future__ import annotations

import base64
import socketserver
import threading
import unittest

from proxy_auth_bridge import (
    ProxyConnectionError,
    _authorization_value,
    _rewrite_http_request,
    check_http_proxy,
)


class _FakeProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        data = bytearray()
        while b"\r\n\r\n" not in data:
            chunk = self.request.recv(4096)
            if not chunk:
                break
            data.extend(chunk)
        text = data.decode("iso-8859-1", errors="replace")
        self.server.last_request = text
        expected = self.server.expected_authorization
        if f"Proxy-Authorization: {expected}" not in text:
            self.request.sendall(
                b"HTTP/1.1 407 Proxy Authentication Required\r\nContent-Length: 0\r\n\r\n"
            )
            return
        self.request.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")


class _FakeProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True


class ProxyAuthBridgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = _FakeProxyServer(("127.0.0.1", 0), _FakeProxyHandler)
        self.server.expected_authorization = _authorization_value("user", "pass")
        self.server.last_request = ""
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_proxy_check_sends_basic_auth_and_connects_to_nemexia(self) -> None:
        result = check_http_proxy(
            "127.0.0.1",
            self.server.server_address[1],
            "user",
            "pass",
            target_host="game.ares.nemexia.com",
            timeout=2,
        )
        self.assertTrue(result["ok"])
        self.assertIn("CONNECT game.ares.nemexia.com:443 HTTP/1.1", self.server.last_request)
        self.assertIn("Proxy-Authorization: Basic ", self.server.last_request)

    def test_proxy_check_rejects_wrong_credentials(self) -> None:
        with self.assertRaisesRegex(ProxyConnectionError, "407"):
            check_http_proxy(
                "127.0.0.1",
                self.server.server_address[1],
                "wrong",
                "credentials",
                timeout=2,
            )

    def test_http_request_rewrite_injects_auth_and_disables_keepalive(self) -> None:
        header = (
            b"GET http://example.test/path HTTP/1.1\r\n"
            b"Host: example.test\r\n"
            b"Proxy-Authorization: Basic OLD\r\n"
            b"Connection: keep-alive\r\n\r\n"
        )
        rewritten = _rewrite_http_request(header, _authorization_value("user", "pass")).decode("iso-8859-1")
        expected = base64.b64encode(b"user:pass").decode("ascii")
        self.assertIn(f"Proxy-Authorization: Basic {expected}", rewritten)
        self.assertNotIn("Basic OLD", rewritten)
        self.assertIn("Connection: close", rewritten)
        self.assertIn("Proxy-Connection: close", rewritten)


if __name__ == "__main__":
    unittest.main()
