import asyncio
import json
import logging
import os
import socket
import ssl
import sys
from pathlib import Path

import aiohttp
import pytest
import trustme

from ominis_src import proxy_handler


async def certificate_origin(servers, tmp_path, hostname="127.0.0.1"):
    ca = trustme.CA()
    certificate = ca.issue_cert(hostname)
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    certificate.configure_cert(server_context)
    endpoint = await servers.origin(server_context, body=b"127.0.0.1")
    ca_path = tmp_path / "ca.pem"
    ca.cert_pem.write_to_path(ca_path)
    return endpoint, ca_path, "https://127.0.0.1:{}".format(endpoint.port)


@pytest.mark.asyncio
async def test_source_fetch_uses_session_trusted_ca(servers, tmp_path):
    origin, ca_path, url = await certificate_origin(servers, tmp_path)
    context = ssl.create_default_context(cafile=str(ca_path))
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=context)) as session:
        assert await proxy_handler.fetch_with_retry(session, url, max_retries=1) == "127.0.0.1"
    assert len(origin.requests) == 1


@pytest.mark.asyncio
async def test_source_fetch_rejects_untrusted_ca(servers, tmp_path):
    origin, _, url = await certificate_origin(servers, tmp_path)
    async with aiohttp.ClientSession() as session:
        assert await proxy_handler.fetch_with_retry(session, url, max_retries=1) is None
    assert origin.requests == []


@pytest.mark.asyncio
async def test_source_fetch_rejects_wrong_hostname(servers, tmp_path):
    origin, ca_path, url = await certificate_origin(servers, tmp_path, hostname="wrong.invalid")
    context = ssl.create_default_context(cafile=str(ca_path))
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=context)) as session:
        assert await proxy_handler.fetch_with_retry(session, url, max_retries=1) is None
    assert origin.requests == []


@pytest.mark.asyncio
async def test_scraping_does_not_disable_source_tls(servers, tmp_path, monkeypatch):
    origin, _, url = await certificate_origin(servers, tmp_path)
    monkeypatch.setattr(proxy_handler, "PROXY_SOURCES", [url])
    assert await proxy_handler.scrape_proxies() == []
    assert origin.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("failure,reason", [
    ("tls", "ClientConnectorCertificateError"),
    ("connection", "ClientConnectorError"),
    ("http", "HTTP 503"),
])
async def test_partial_source_failure_logs_warning(servers, tmp_path, caplog, failure, reason):
    html = b"<table><tr><td>127.0.0.1</td><td>8080</td></tr></table>"
    healthy = await servers.origin(body=html)
    if failure == "tls":
        _, _, failed_url = await certificate_origin(servers, tmp_path)
    elif failure == "connection":
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            failed_url = "http://127.0.0.1:{}".format(reserved.getsockname()[1])
    else:
        async def unavailable(reader, writer, endpoint):
            endpoint.requests.append(await reader.readuntil(b"\r\n\r\n"))
            writer.write(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
        failed_url = (await servers.start(unavailable)).url

    with caplog.at_level(logging.WARNING, logger=proxy_handler.__name__):
        async with aiohttp.ClientSession() as session:
            failed, successful = await asyncio.gather(
                proxy_handler.fetch_proxies_from_source(session, failed_url),
                proxy_handler.fetch_proxies_from_source(session, healthy.url),
            )
    assert failed == set()
    assert successful == {"127.0.0.1:8080"}
    warnings = [record for record in caplog.records
                if record.name == proxy_handler.__name__ and record.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert failed_url in warnings[0].getMessage()
    assert reason in warnings[0].getMessage()
    assert "2 attempts" in warnings[0].getMessage()
    assert healthy.url not in warnings[0].getMessage()


@pytest.mark.asyncio
async def test_recovered_source_does_not_log_exhaustion_warning(servers, caplog):
    async def recovering(reader, writer, endpoint):
        endpoint.requests.append(await reader.readuntil(b"\r\n\r\n"))
        status = b"503 Service Unavailable" if len(endpoint.requests) == 1 else b"200 OK"
        writer.write(b"HTTP/1.1 " + status + b"\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        await writer.drain()

    source = await servers.start(recovering)
    with caplog.at_level(logging.WARNING, logger=proxy_handler.__name__):
        async with aiohttp.ClientSession() as session:
            assert await proxy_handler.fetch_with_retry(session, source.url, max_retries=2) == "ok"
    assert len(source.requests) == 2
    assert not [record for record in caplog.records
                if record.name == proxy_handler.__name__ and record.levelno >= logging.WARNING]


@pytest.mark.asyncio
@pytest.mark.parametrize("certificate_kind", ["trusted", "untrusted", "wrong_hostname"])
async def test_proxy_validation_verifies_target_tls(servers, tmp_path, certificate_kind):
    hostname = "wrong.invalid" if certificate_kind == "wrong_hostname" else "127.0.0.1"
    origin, ca_path, url = await certificate_origin(servers, tmp_path, hostname)
    proxy = await servers.http_proxy()
    address = "127.0.0.1:{}".format(proxy.port)
    code = """
import asyncio, json, sys
from ominis_src import proxy_handler as handler
handler.TEST_URLS = [sys.argv[1]]
handler.MAX_RETRIES = 1
handler.MIN_DELAY = handler.MAX_DELAY = 0
handler.get_random_headers = lambda: {'User-Agent': 'Ominis-test'}
print(json.dumps(asyncio.run(handler.validate_proxy_batch([sys.argv[2]]))))
"""
    env = os.environ.copy()
    if certificate_kind != "untrusted":
        env["SSL_CERT_FILE"] = str(ca_path)
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-c", code, url, address,
        cwd=Path(__file__).resolve().parents[1], env=env,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15)
    assert process.returncode == 0, stderr.decode()
    valid = json.loads(stdout)
    if certificate_kind == "trusted":
        assert valid == [address]
        assert len(origin.requests) == 1
    else:
        assert valid == []
        assert origin.requests == []
    assert proxy.requests[0]["method"] == "CONNECT"
