"""Username checks: URL building, parsing, concurrency and reports."""

import csv
import json
from pathlib import Path

import httpx
import pytest

from ominis_src import username


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("base,expected", [
    ("https://example.com/", "https://example.com/acme"),
    ("https://example.com/@", "https://example.com/@acme"),
    ("https://example.com/user/", "https://example.com/user/acme"),
    ("https://example.com/u", "https://example.com/u/acme"),
])
def test_profile_url_handles_templates(base, expected):
    assert username.profile_url(base, "acme") == expected


def test_profile_url_rejects_empty_templates():
    with pytest.raises(ValueError, match="empty platform"):
        username.profile_url("   ", "acme")


def test_load_platforms_skips_comments(tmp_path):
    path = tmp_path / "urls.txt"
    path.write_text("# comment\nhttps://a.example/\n\n  https://b.example/  \n",
                    encoding="utf-8")
    assert username.load_platforms(path) == ["https://a.example/", "https://b.example/"]


def test_parse_page_reads_title_and_description():
    title, description = username.parse_page(
        "<html><head><title>Acme on Example</title>"
        '<meta name="description" content="The acme page"></head></html>', "acme")
    assert title == "Acme on Example"
    assert description == "The acme page"


@pytest.mark.asyncio
async def test_check_one_matches_title():
    def handler(request):
        assert str(request.url) == "https://example.com/acme"
        return httpx.Response(200, text="<title>Acme profile</title>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.found
    assert hit.status == 200
    assert hit.title == "Acme profile"


@pytest.mark.asyncio
async def test_check_one_falls_back_to_the_body():
    def handler(request):
        return httpx.Response(200, text="<title>Profile</title><p>I am Acme</p>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.found


@pytest.mark.asyncio
async def test_check_one_reports_a_missing_profile():
    def handler(request):
        return httpx.Response(200, text="<title>Not found</title>nothing here")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.status == 200
    assert hit.matched is False
    assert hit.found is False


@pytest.mark.asyncio
async def test_check_one_keeps_non_200_statuses():
    def handler(request):
        return httpx.Response(404, text="gone")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.status == 404
    assert hit.found is False


@pytest.mark.asyncio
async def test_check_one_records_transport_errors():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert "ConnectError" in hit.error
    assert hit.found is False


class _FakeClient:
    instances = []
    bodies = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, timeout=None, follow_redirects=True):
        body = _FakeClient.bodies.get(url, "<title>miss</title>")
        return httpx.Response(200, text=body, request=httpx.Request("GET", url))


@pytest.mark.asyncio
async def test_run_checks_every_template_and_passes_proxy(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.bodies = {"https://a.example/acme": "<title>acme</title>"}
    monkeypatch.setattr(username.httpx, "AsyncClient", _FakeClient)
    seen = []
    outcome = await username.run(
        "acme", ["https://a.example/", "https://b.example/"],
        concurrency=2, proxies=("127.0.0.1:8080",),
        progress=seen.append)
    assert len(outcome.hits) == 2
    assert len(outcome.found) == 1
    assert len(seen) == 2
    assert _FakeClient.instances[0].kwargs["proxy"] == "http://127.0.0.1:8080"
    assert _FakeClient.instances[0].kwargs["verify"] is True


@pytest.mark.asyncio
async def test_run_rejects_unsafe_usernames():
    with pytest.raises(ValueError, match="letters, digits"):
        await username.run("../etc", ["https://a.example/"])


@pytest.mark.asyncio
async def test_run_requires_platforms():
    with pytest.raises(ValueError, match="no platform URLs"):
        await username.run("acme", [])


def _report():
    return username.UsernameReport(username="acme", hits=[
        username.Hit(username="acme", url="https://a.example/acme", status=200,
                     title="Acme", matched=True),
        username.Hit(username="acme", url="https://b.example/acme",
                     error="ConnectError: no route"),
    ])


def test_write_produces_every_requested_format(tmp_path):
    written = username.write(_report(), tmp_path, ("txt", "json", "csv", "md"))
    assert set(written) == {"txt", "json", "csv", "md"}
    assert written["txt"].endswith("username-acme.txt")
    payload = json.loads(Path(written["json"]).read_text(encoding="utf-8"))
    assert payload["found"] == 1
    assert payload["checked"] == 2
    assert payload["profiles"][0]["url"] == "https://a.example/acme"
    with Path(written["csv"]).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert "found **1** profiles" in Path(written["md"]).read_text(encoding="utf-8")
    assert "Found 1 of 2 platforms." in Path(written["txt"]).read_text(encoding="utf-8")


def test_write_defaults_to_txt(tmp_path):
    written = username.write(_report(), tmp_path, ("txt",))
    assert Path(written["txt"]).name == "username-acme.txt"
