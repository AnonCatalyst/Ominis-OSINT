"""Username checks: URL building, parsing, concurrency and reports."""

import csv
import json
from pathlib import Path

import httpx
import pytest

from ominis_src import username


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_only_the_proactor_reset_callback_is_silenced():
    reset = {"exception": ConnectionResetError(10054, "reset"),
             "message": "Exception in callback "
                        "_ProactorBasePipeTransport._call_connection_lost(None)"}
    assert username._is_transport_reset(reset)
    assert not username._is_transport_reset(
        {"exception": ValueError("boom"), "message": reset["message"]})
    assert not username._is_transport_reset(
        {"exception": ConnectionResetError(10054, "reset"),
         "message": "Fatal error on transport"})
    assert not username._is_transport_reset({})


@pytest.mark.parametrize("base,expected", [
    ("https://example.com/", "https://example.com/acme"),
    ("https://example.com/@", "https://example.com/@acme"),
    ("https://example.com/user/", "https://example.com/user/acme"),
    ("https://example.com/u", "https://example.com/u/acme"),
    ("https://example.com/profile?gamertag=",
     "https://example.com/profile?gamertag=acme"),
    ("https://example.com/search?u=", "https://example.com/search?u=acme"),
    ("https://example.com/{username}", "https://example.com/acme"),
    ("https://wikipedia.org/wiki/user:", "https://wikipedia.org/wiki/user:acme"),
    ("https://pinboard.in/u:", "https://pinboard.in/u:acme"),
    ("https://example.com/photodb/user?",
     "https://example.com/photodb/user?acme"),
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


def test_load_platforms_drops_a_bom(tmp_path):
    path = tmp_path / "urls.txt"
    path.write_text("https://a.example/\nhttps://b.example/\n",
                    encoding="utf-8-sig")
    assert username.load_platforms(path) == [
        "https://a.example/", "https://b.example/"]


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
async def test_check_one_ignores_substrings_and_canonical_links():
    def handler(request):
        return httpx.Response(
            200,
            text='<title>AcmeCorp news</title>'
                 '<link rel="canonical" href="https://example.com/acme">'
                 "<p>AcmeCorp is hiring</p>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.found is False


@pytest.mark.asyncio
async def test_check_one_rejects_a_soft_404_with_a_canonical_link():
    def handler(request):
        return httpx.Response(
            200,
            text='<title>Profile</title>'
                 '<link rel="canonical" href="https://example.com/acme">'
                 "<p>User not found</p>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.found is False


@pytest.mark.asyncio
async def test_check_one_does_not_treat_a_trailing_slash_as_a_redirect():
    def handler(request):
        return httpx.Response(
            200, text="<title>Reddit</title>",
            request=httpx.Request("GET", "https://example.com/acme/"))

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.found is False


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
async def test_run_normalises_a_leading_at_sign(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.bodies = {"https://a.example/acme": "<title>acme</title>"}
    monkeypatch.setattr(username.httpx, "AsyncClient", _FakeClient)
    outcome = await username.run("@acme", ["https://a.example/"])
    assert outcome.username == "acme"
    assert [hit.url for hit in outcome.hits] == ["https://a.example/acme"]


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


def test_write_keeps_dots_in_a_username(tmp_path):
    outcome = username.UsernameReport(username="john.doe", hits=[])
    written = username.write(outcome, tmp_path, ("txt", "json"))
    assert Path(written["txt"]).name == "username-john.doe.txt"
    assert Path(written["json"]).name == "username-john.doe.json"


@pytest.mark.asyncio
async def test_check_one_labels_an_unregistered_host():
    def handler(request):
        return httpx.Response(200, text="<title>acme</title>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://bionluk.com/")
    assert hit.found
    assert hit.platform == "Bionluk"
    assert hit.category == ""


@pytest.mark.asyncio
async def test_check_one_labels_the_detected_platform():
    def handler(request):
        return httpx.Response(200, text="<title>acme</title>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://github.com/")
    assert hit.platform == "GitHub"
    assert hit.category == "dev"
    assert hit.confidence == 90


@pytest.mark.asyncio
async def test_check_one_uses_open_graph_metadata():
    def handler(request):
        return httpx.Response(
            200,
            text='<title>Profile</title>'
                 '<meta property="og:title" content="Acme on Example">')

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.found
    assert hit.match == "metadata"


@pytest.mark.asyncio
async def test_check_one_uses_a_structured_handle():
    def handler(request):
        return httpx.Response(
            200,
            text='<title>TikTok</title><script>window.__DATA__='
                 '{"uniqueId":"acme","nickname":"Acme"}</script>')

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://tiktok.com/")
    assert hit.found
    assert hit.match == "structured"


@pytest.mark.asyncio
async def test_check_one_trusts_twitch_canonical_url():
    def handler(request):
        return httpx.Response(
            200,
            text='<title>Twitch</title>'
                 '<link rel="canonical" href="https://www.twitch.tv/acme">')

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://twitch.tv/")
    assert hit.found
    assert hit.match == "canonical"


@pytest.mark.asyncio
async def test_check_one_ignores_twitch_not_found_without_a_canonical():
    def handler(request):
        return httpx.Response(200, text="<title>Twitch</title><p>Not here</p>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://twitch.tv/")
    assert hit.found is False


@pytest.mark.asyncio
async def test_check_one_rejects_an_embedded_404():
    # Pinterest returns HTTP 200 for a missing profile and still includes the
    # requested username in its JSON state.
    def handler(request):
        return httpx.Response(
            200, text='<title>Pinterest</title>'
                      '<script>{"username":"acme","httpStatus":404}</script>')

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://pinterest.com/")
    assert hit.found is False


@pytest.mark.asyncio
async def test_check_one_rejects_a_localised_missing_title():
    def handler(request):
        return httpx.Response(
            200,
            text="<title>Warface | Профиль игрока acme не существует</title>"
                 "<p>acme</p>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://example.com/")
    assert hit.found is False


def test_error_text_is_never_blank():
    text = username._error_text(httpx.ConnectTimeout(""))
    assert text.startswith("ConnectTimeout:")
    assert "timed out" in text


@pytest.mark.asyncio
async def test_check_one_reads_a_title_beyond_the_old_scan_window():
    padding = "<script>" + ("x" * 300_000) + "</script>"

    def handler(request):
        return httpx.Response(
            200, text=f"<html><head>{padding}<title>acme on YouTube</title>"
                      "</head></html>")

    async with _client(handler) as client:
        hit = await username.check_one(client, "acme", "https://youtube.com/")
    assert hit.found
    assert hit.title == "acme on YouTube"


@pytest.mark.asyncio
async def test_run_dedupes_templates_and_puts_matches_first(monkeypatch):
    _FakeClient.instances = []
    _FakeClient.bodies = {"https://b.example/acme": "<title>acme</title>"}
    monkeypatch.setattr(username.httpx, "AsyncClient", _FakeClient)
    outcome = await username.run(
        "acme", ["https://a.example/", "https://b.example/",
                 "https://a.example/"])
    assert len(outcome.hits) == 2
    assert outcome.hits[0].found
    assert outcome.hits[0].url == "https://b.example/acme"


def test_write_can_include_every_checked_url(tmp_path):
    written = username.write(_report(), tmp_path, ("json", "txt", "md"),
                             include_all=True)
    payload = json.loads(Path(written["json"]).read_text(encoding="utf-8"))
    assert len(payload["hits"]) == 2
    text = Path(written["txt"]).read_text(encoding="utf-8")
    assert "All checked" in text
    assert "https://b.example/acme" in text
    markdown = Path(written["md"]).read_text(encoding="utf-8")
    assert "## All checked" in markdown
