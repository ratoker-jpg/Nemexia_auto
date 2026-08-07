from __future__ import annotations

import base64
import select
import socket
import socketserver
import subprocess
import threading
from pathlib import Path
from typing import Any

from browser import BrowserAutomationError, find_yandex_browser
from config import FLEETS_URL, PROFILE_DIR


MAX_HEADER_BYTES = 64 * 1024
RELAY_BUFFER = 64 * 1024


class ProxyConnectionError(BrowserAutomationError):
    """The configured upstream proxy cannot be used safely."""


def _authorization_value(username: str, password: str) -> str:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def _read_headers(sock: socket.socket, *, limit: int = MAX_HEADER_BYTES) -> tuple[bytes, bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(8192)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > limit:
            raise ProxyConnectionError("Ответ прокси содержит слишком большие заголовки")
    marker = data.find(b"\r\n\r\n")
    if marker < 0:
        return bytes(data), b""
    marker += 4
    return bytes(data[:marker]), bytes(data[marker:])


def _response_status(header: bytes) -> tuple[int | None, str]:
    first = header.split(b"\r\n", 1)[0].decode("iso-8859-1", errors="replace")
    parts = first.split(" ", 2)
    try:
        code = int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        code = None
    return code, first


def check_http_proxy(
    host: str,
    port: int,
    username: str,
    password: str,
    *,
    target_host: str = "game.ares.nemexia.com",
    target_port: int = 443,
    timeout: float = 8.0,
) -> dict[str, Any]:
    """Verify proxy reachability, credentials and CONNECT access to Nemexia."""
    host = str(host or "").strip()
    username = str(username or "")
    password = str(password or "")
    if not host:
        raise ProxyConnectionError("Не указан IP или хост прокси")
    if int(port) < 1 or int(port) > 65535:
        raise ProxyConnectionError("Порт прокси должен быть в диапазоне 1–65535")
    if not username or not password:
        raise ProxyConnectionError("Для этого режима нужны логин и пароль HTTP-прокси")

    request = (
        f"CONNECT {target_host}:{int(target_port)} HTTP/1.1\r\n"
        f"Host: {target_host}:{int(target_port)}\r\n"
        f"Proxy-Authorization: {_authorization_value(username, password)}\r\n"
        "Proxy-Connection: close\r\n"
        "Connection: close\r\n\r\n"
    ).encode("iso-8859-1")

    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as upstream:
            upstream.settimeout(timeout)
            upstream.sendall(request)
            header, _ = _read_headers(upstream)
    except (OSError, TimeoutError) as exc:
        raise ProxyConnectionError(f"Прокси {host}:{port} недоступен: {exc}") from exc

    status, status_line = _response_status(header)
    if status == 407:
        raise ProxyConnectionError("Прокси отклонил логин или пароль (HTTP 407)")
    if status is None or not 200 <= status < 300:
        raise ProxyConnectionError(
            f"Прокси не открыл соединение с Nemexia: {status_line or 'неизвестный ответ'}"
        )
    return {
        "ok": True,
        "proxy": f"{host}:{int(port)}",
        "target": f"{target_host}:{int(target_port)}",
        "status": status,
    }


def _rewrite_http_request(header: bytes, authorization: str) -> bytes:
    text = header.decode("iso-8859-1", errors="replace")
    lines = text.split("\r\n")
    if not lines or not lines[0]:
        raise ProxyConnectionError("Браузер прислал пустой HTTP-запрос")
    request_line = lines[0]
    parts = request_line.split(" ", 2)
    if len(parts) != 3:
        raise ProxyConnectionError("Некорректная первая строка HTTP-запроса")
    method, target, version = parts
    headers: list[tuple[str, str]] = []
    host_header = ""
    for line in lines[1:]:
        if not line or ":" not in line:
            continue
        name, value = line.split(":", 1)
        key = name.strip().casefold()
        clean_value = value.strip()
        if key == "host":
            host_header = clean_value
        if key in {"proxy-authorization", "proxy-connection", "connection"}:
            continue
        headers.append((name.strip(), clean_value))

    if target.startswith("/") and host_header:
        target = f"http://{host_header}{target}"
    output = [f"{method} {target} {version}"]
    output.extend(f"{name}: {value}" for name, value in headers)
    output.append(f"Proxy-Authorization: {authorization}")
    output.append("Proxy-Connection: close")
    output.append("Connection: close")
    return ("\r\n".join(output) + "\r\n\r\n").encode("iso-8859-1")


def _relay(client: socket.socket, upstream: socket.socket, *, idle_timeout: float = 180.0) -> None:
    sockets = [client, upstream]
    while True:
        readable, _, exceptional = select.select(sockets, [], sockets, idle_timeout)
        if exceptional or not readable:
            return
        for source in readable:
            destination = upstream if source is client else client
            try:
                chunk = source.recv(RELAY_BUFFER)
            except OSError:
                return
            if not chunk:
                return
            try:
                destination.sendall(chunk)
            except OSError:
                return


class _ProxyRequestHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, _ProxyServer)
        client = self.request
        assert isinstance(client, socket.socket)
        client.settimeout(server.connect_timeout)
        try:
            request_header, request_rest = _read_headers(client)
            if not request_header:
                return
            first = request_header.split(b"\r\n", 1)[0].decode("iso-8859-1", errors="replace")
            parts = first.split(" ", 2)
            if len(parts) != 3:
                return
            method, target, _ = parts
            with socket.create_connection(
                (server.upstream_host, server.upstream_port),
                timeout=server.connect_timeout,
            ) as upstream:
                upstream.settimeout(server.connect_timeout)
                if method.upper() == "CONNECT":
                    connect_request = (
                        f"CONNECT {target} HTTP/1.1\r\n"
                        f"Host: {target}\r\n"
                        f"Proxy-Authorization: {server.authorization}\r\n"
                        "Proxy-Connection: keep-alive\r\n\r\n"
                    ).encode("iso-8859-1")
                    upstream.sendall(connect_request)
                    response_header, response_rest = _read_headers(upstream)
                    client.sendall(response_header)
                    status, _ = _response_status(response_header)
                    if status is None or not 200 <= status < 300:
                        return
                    if response_rest:
                        client.sendall(response_rest)
                    if request_rest:
                        upstream.sendall(request_rest)
                    _relay(client, upstream)
                    return

                upstream.sendall(_rewrite_http_request(request_header, server.authorization))
                if request_rest:
                    upstream.sendall(request_rest)
                _relay(client, upstream)
        except Exception:
            try:
                client.sendall(
                    b"HTTP/1.1 502 Bad Gateway\r\nConnection: close\r\nContent-Length: 0\r\n\r\n"
                )
            except OSError:
                pass


class _ProxyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        upstream_host: str,
        upstream_port: int,
        username: str,
        password: str,
        connect_timeout: float,
    ) -> None:
        self.upstream_host = upstream_host
        self.upstream_port = int(upstream_port)
        self.authorization = _authorization_value(username, password)
        self.connect_timeout = float(connect_timeout)
        super().__init__(address, _ProxyRequestHandler)


class AuthenticatedProxyBridge:
    """Local unauthenticated HTTP proxy that authenticates to one upstream proxy."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
        connect_timeout: float = 12.0,
    ) -> None:
        self._server = _ProxyServer(
            (listen_host, int(listen_port)),
            str(host).strip(),
            int(port),
            str(username),
            str(password),
            connect_timeout,
        )
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    def start(self) -> int:
        if self._thread and self._thread.is_alive():
            return self.port
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="nemexia-proxy-auth",
            daemon=True,
        )
        self._thread.start()
        return self.port

    def stop(self) -> None:
        try:
            self._server.shutdown()
        except Exception:
            pass
        try:
            self._server.server_close()
        except Exception:
            pass
        self._thread = None


def launch_yandex_via_local_proxy(cdp_port: int, proxy_port: int) -> subprocess.Popen[Any]:
    """Launch the dedicated Yandex profile with no direct-network fallback for web traffic."""
    executable = find_yandex_browser()
    if executable is None:
        raise BrowserAutomationError("Яндекс Браузер не найден в стандартных папках")
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        str(executable),
        f"--remote-debugging-port={int(cdp_port)}",
        f"--user-data-dir={PROFILE_DIR}",
        f"--proxy-server=http://127.0.0.1:{int(proxy_port)}",
        "--no-first-run",
        "--no-default-browser-check",
        FLEETS_URL,
    ]
    try:
        return subprocess.Popen(command, cwd=Path(PROFILE_DIR))
    except OSError as exc:
        raise BrowserAutomationError(f"Не удалось запустить Яндекс Браузер: {exc}") from exc
