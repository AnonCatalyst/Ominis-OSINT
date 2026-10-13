import logging
import socket
import ssl
import subprocess
import sys
from pathlib import Path

import pytest
import trustme

from ominis_src import tools_handler


@pytest.mark.parametrize("proxy,expected", [
    ("127.0.0.1:8080", "http://127.0.0.1:8080"),
    (" localhost:8080 ", "http://localhost:8080"),
    ("[::1]:8080", "http://[::1]:8080"),
    ("http://localhost:8080", "http://localhost:8080"),
    ("https://localhost:8080/", "https://localhost:8080"),
    ("socks5://localhost:1080", "socks5://localhost:1080"),
    ("socks5h://localhost:1080", "socks5h://localhost:1080"),
    ("http://alice:p%40ss@localhost:8080", "http://alice:p%40ss@localhost:8080"),
])
def test_normalize_proxy(proxy, expected):
    assert tools_handler._normalize_proxy(proxy) == expected


@pytest.mark.parametrize("proxy", [
    "", "  ", None, 123, "localhost", "http://", "ftp://localhost:8080",
    "http://localhost:0", "http://localhost:65536", "http://localhost:not-a-port",
    "http://localhost:", "2001:db8::1:8080", "http://local host:8080",
    "http://localhost:8080/path", "http://localhost:8080?route=1",
    "http://localhost:8080#fragment", "http://localhost:8080\n",
])
def test_invalid_proxy_is_rejected(proxy):
    with pytest.raises(ValueError):
        tools_handler._normalize_proxy(proxy)


@pytest.mark.asyncio
@pytest.mark.parametrize("qualified", [False, True])
async def test_explicit_proxy_routes_request(servers, qualified):
    origin = await servers.origin()
    proxy = await servers.http_proxy()
    address = proxy.url if qualified else "127.0.0.1:{}".format(proxy.port)
    result = await tools_handler.make_request_async(origin.url + "/probe?q=1", [address])
    assert result == "local response"
    assert len(proxy.requests) == 1
    assert proxy.requests[0]["target"] == origin.url + "/probe?q=1"
    assert origin.requests[0].startswith("GET /probe?q=1 HTTP/1.1")


@pytest.mark.asyncio
async def test_explicit_proxy_overrides_environment_and_no_proxy(servers, monkeypatch):
    origin = await servers.origin()
    explicit = await servers.http_proxy()
    environment = await servers.http_proxy()
    monkeypatch.setenv("HTTP_PROXY", environment.url)
    monkeypatch.setenv("ALL_PROXY", environment.url)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    assert await tools_handler.make_request_async(origin.url, [explicit.url]) == "local response"
    assert len(explicit.requests) == 1
    assert environment.requests == []


@pytest.mark.asyncio
async def test_unsupplied_pool_preserves_environment_proxy(servers, monkeypatch):
    origin = await servers.origin()
    proxy = await servers.http_proxy()
    monkeypatch.setenv("HTTP_PROXY", proxy.url)
    assert await tools_handler.make_request_async(origin.url) == "local response"
    assert len(proxy.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("pool", [[], [""], ["ftp://localhost:8080"],
                                  ["127.0.0.1:8080", "invalid"], "127.0.0.1:8080"])
async def test_invalid_pool_fails_before_origin_connection(servers, pool):
    origin = await servers.origin()
    with pytest.raises(ValueError):
        await tools_handler.make_request_async(origin.url, pool)
    assert origin.connections == 0


@pytest.mark.asyncio
async def test_failed_proxy_never_falls_back_to_direct(servers):
    origin = await servers.origin()
    with socket.socket() as reserved:
        reserved.bind(("127.0.0.1", 0))
        port = reserved.getsockname()[1]
    with pytest.raises(RuntimeError, match="Request failed"):
        await tools_handler.make_request_async(origin.url, ["127.0.0.1:{}".format(port)])
    assert origin.connections == 0


async def https_origin(servers, tmp_path, monkeypatch, trusted=True, hostname="127.0.0.1"):
    ca = trustme.CA()
    certificate = ca.issue_cert(hostname)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    certificate.configure_cert(context)
    origin = await servers.origin(context)
    if trusted:
        ca_path = tmp_path / "ca.pem"
        ca.cert_pem.write_to_path(ca_path)
        monkeypatch.setenv("SSL_CERT_FILE", str(ca_path))
    return origin, "https://127.0.0.1:{}".format(origin.port)


@pytest.mark.asyncio
async def test_connect_proxy_and_trusted_ca(servers, tmp_path, monkeypatch):
    origin, url = await https_origin(servers, tmp_path, monkeypatch)
    proxy = await servers.http_proxy()
    assert await tools_handler.make_request_async(url, [proxy.url]) == "local response"
    assert proxy.requests[0]["method"] == "CONNECT"
    assert len(origin.requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("via_proxy", [False, True])
async def test_untrusted_certificate_is_rejected(servers, tmp_path, monkeypatch, via_proxy):
    origin, url = await https_origin(servers, tmp_path, monkeypatch, trusted=False)
    proxy = await servers.http_proxy() if via_proxy else None
    with pytest.raises(RuntimeError, match="Request failed"):
        await tools_handler.make_request_async(url, [proxy.url] if proxy else None)
    assert origin.requests == []
    if proxy:
        assert len(proxy.requests) == 1


@pytest.mark.asyncio
async def test_wrong_hostname_certificate_is_rejected(servers, tmp_path, monkeypatch):
    origin, url = await https_origin(servers, tmp_path, monkeypatch, hostname="wrong.invalid")
    with pytest.raises(RuntimeError, match="Request failed"):
        await tools_handler.make_request_async(url)
    assert origin.requests == []


@pytest.mark.asyncio
async def test_authenticated_proxy_redacts_display(servers, monkeypatch, capsys):
    origin = await servers.origin()
    proxy = await servers.http_proxy(credentials="route-user:p@ss")
    monkeypatch.setattr(tools_handler, "show_message", True)
    url = "http://route-user:p%40ss@127.0.0.1:{}".format(proxy.port)
    assert await tools_handler.make_request_async(origin.url, [url]) == "local response"
    output = capsys.readouterr().out
    assert "127.0.0.1:{}".format(proxy.port) in output
    assert "route-user" not in output and "p%40ss" not in output and "p@ss" not in output


@pytest.mark.asyncio
async def test_proxy_credentials_are_not_logged_on_failure(servers, caplog):
    proxy = await servers.http_proxy(credentials="route-user:private-pass",
                                     reject_reason="route-user private-pass")
    url = "http://route-user:private-pass@127.0.0.1:{}".format(proxy.port)
    with caplog.at_level(logging.ERROR), pytest.raises(RuntimeError):
        await tools_handler.make_request_async("https://127.0.0.1:1", [url])
    assert len(proxy.requests) == 1
    assert "route-user" not in caplog.text and "private-pass" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("scheme", ["socks5", "socks5h"])
async def test_socks_proxy_routes_request(servers, scheme):
    origin = await servers.origin()
    proxy = await servers.socks_proxy()
    url = "{}://127.0.0.1:{}".format(scheme, proxy.port)
    assert await tools_handler.make_request_async(origin.url, [url]) == "local response"
    assert proxy.requests == [("127.0.0.1", origin.port)]


@pytest.mark.parametrize("module", ["ominis_src.tools_handler", "ominis"])
def test_import_preserves_https_verification_and_warnings(module):
    code = """
import importlib, ssl, warnings
from urllib3.exceptions import InsecureRequestWarning
original = ssl._create_default_https_context
importlib.import_module(MODULE)
assert ssl._create_default_https_context is original
with warnings.catch_warnings(record=True) as recorded:
    warnings.warn('test TLS warning', InsecureRequestWarning)
assert len(recorded) == 1
""".replace("MODULE", repr(module))
    result = subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
