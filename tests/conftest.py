"""Loopback-only origins and proxies for real HTTP client regression tests."""
import asyncio
import base64
import contextlib
import ipaddress
import socket
import ssl
import struct
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import pytest
import pytest_asyncio

from ominis_src import proxy_handler, tools_handler


def is_local(host):
    if isinstance(host, bytes):
        host = host.decode("ascii")
    if host in (None, "localhost"):
        return True
    try:
        return ipaddress.ip_address(host.split("%", 1)[0]).is_loopback
    except (ValueError, AttributeError):
        return False


@pytest.fixture(autouse=True)
def local_network_only(monkeypatch):
    """Fail before public DNS resolution or an outbound non-loopback connection."""
    resolve = socket.getaddrinfo
    connect = socket.socket.connect
    connect_ex = socket.socket.connect_ex

    def local_resolve(host, *args, **kwargs):
        assert is_local(host), "Tests may only resolve loopback hosts"
        return resolve(host, *args, **kwargs)

    def local_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            assert is_local(address[0]), "Tests may only connect to loopback"
        return connect(sock, address)

    def local_connect_ex(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            assert is_local(address[0]), "Tests may only connect to loopback"
        return connect_ex(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", local_resolve)
    monkeypatch.setattr(socket.socket, "connect", local_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", local_connect_ex)


@pytest.fixture(autouse=True)
def deterministic_requests(monkeypatch):
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
                 "http_proxy", "https_proxy", "all_proxy", "no_proxy",
                 "SSL_CERT_FILE", "SSL_CERT_DIR"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(tools_handler, "MAX_RETRY_COUNT", 1)
    monkeypatch.setattr(tools_handler, "show_message", False)
    monkeypatch.setattr(tools_handler, "USER_AGENTS", ["Ominis-test"])
    monkeypatch.setattr(tools_handler.random, "uniform", lambda *args: 0)
    monkeypatch.setattr(proxy_handler, "MAX_RETRIES", 1)
    monkeypatch.setattr(proxy_handler, "get_random_headers", lambda: {"User-Agent": "Ominis-test"})


@dataclass
class Endpoint:
    port: int
    requests: list = field(default_factory=list)
    connections: int = 0

    @property
    def url(self):
        return "http://127.0.0.1:{}".format(self.port)


class LocalServers:
    def __init__(self):
        self.servers = []
        self.tasks = set()
        self.errors = []

    async def start(self, handler, ssl_context=None):
        endpoint = Endpoint(0)

        async def tracked(reader, writer):
            task = asyncio.current_task()
            self.tasks.add(task)
            endpoint.connections += 1
            try:
                await handler(reader, writer, endpoint)
            except (asyncio.IncompleteReadError, ConnectionError, ssl.SSLError):
                pass
            except Exception as exc:
                self.errors.append(exc)
            finally:
                writer.close()
                with contextlib.suppress(ConnectionError, ssl.SSLError):
                    await writer.wait_closed()
                self.tasks.discard(task)

        server = await asyncio.start_server(tracked, "127.0.0.1", 0, ssl=ssl_context)
        endpoint.port = server.sockets[0].getsockname()[1]
        self.servers.append(server)
        return endpoint

    async def origin(self, ssl_context=None, body=b"local response"):
        async def serve(reader, writer, endpoint):
            raw = await reader.readuntil(b"\r\n\r\n")
            endpoint.requests.append(raw.decode("latin-1"))
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: " + str(len(body)).encode()
                         + b"\r\nConnection: close\r\n\r\n" + body)
            await writer.drain()
        return await self.start(serve, ssl_context)

    async def relay(self, client_reader, client_writer, remote_reader, remote_writer):
        async def copy(reader, writer):
            while True:
                data = await reader.read(65536)
                if not data:
                    return
                writer.write(data)
                await writer.drain()

        tasks = [asyncio.create_task(copy(client_reader, remote_writer)),
                 asyncio.create_task(copy(remote_reader, client_writer))]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            remote_writer.close()
            with contextlib.suppress(ConnectionError, ssl.SSLError):
                await remote_writer.wait_closed()

    async def http_proxy(self, credentials=None, reject_reason=None):
        async def proxy(reader, writer, endpoint):
            raw = await reader.readuntil(b"\r\n\r\n")
            lines = raw.decode("latin-1").split("\r\n")
            method, target, version = lines[0].split(" ", 2)
            headers = dict(line.split(":", 1) for line in lines[1:] if ":" in line)
            headers = {key.lower(): value.strip() for key, value in headers.items()}
            endpoint.requests.append({"method": method, "target": target, "headers": headers})
            if credentials is not None:
                expected = "Basic " + base64.b64encode(credentials.encode()).decode()
                assert headers.get("proxy-authorization") == expected
            if reject_reason is not None:
                writer.write(b"HTTP/1.1 407 " + reject_reason.encode("ascii")
                             + b"\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            parsed = urlsplit("//" + target) if method == "CONNECT" else urlsplit(target)
            assert is_local(parsed.hostname)
            remote_reader, remote_writer = await asyncio.open_connection(parsed.hostname, parsed.port)
            if method == "CONNECT":
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await writer.drain()
            else:
                path = parsed.path or "/"
                if parsed.query:
                    path += "?" + parsed.query
                forwarded = ["{} {} {}".format(method, path, version)]
                forwarded.extend(line for line in lines[1:] if line and not
                                 line.lower().startswith(("proxy-authorization:", "proxy-connection:")))
                remote_writer.write(("\r\n".join(forwarded) + "\r\n\r\n").encode("latin-1"))
                await remote_writer.drain()
            await self.relay(reader, writer, remote_reader, remote_writer)
        return await self.start(proxy)

    async def socks_proxy(self):
        async def proxy(reader, writer, endpoint):
            version, count = await reader.readexactly(2)
            methods = await reader.readexactly(count)
            assert version == 5 and 0 in methods
            writer.write(b"\x05\x00")
            await writer.drain()
            version, command, reserved, address_type = await reader.readexactly(4)
            assert (version, command, reserved) == (5, 1, 0)
            if address_type == 1:
                host = socket.inet_ntoa(await reader.readexactly(4))
            elif address_type == 3:
                length = (await reader.readexactly(1))[0]
                host = (await reader.readexactly(length)).decode("ascii")
            else:
                assert address_type == 4
                host = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
            port = struct.unpack("!H", await reader.readexactly(2))[0]
            assert is_local(host)
            endpoint.requests.append((host, port))
            remote_reader, remote_writer = await asyncio.open_connection(host, port)
            writer.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x00")
            await writer.drain()
            await self.relay(reader, writer, remote_reader, remote_writer)
        return await self.start(proxy)

    async def close(self):
        for server in self.servers:
            server.close()
        for server in self.servers:
            await server.wait_closed()
        if self.tasks:
            pending = list(self.tasks)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        assert not self.errors, self.errors


@pytest_asyncio.fixture
async def servers():
    local = LocalServers()
    try:
        yield local
    finally:
        await local.close()
