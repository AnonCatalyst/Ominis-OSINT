import asyncio
import json
import os
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
