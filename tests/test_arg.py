"""Offline tests for the ARG build."""

import json

import pytest

from src import tools_handler


DDG = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">A</a>
  <a class="result__snippet">sa</a>
</div>
<div class="result">
  <a class="result__a" href="https://duckduckgo.com/y.js?ad=1">ad</a>
</div>
<div class="result">
  <a class="result__a" href="https://example.org/b">B</a>
</div>
"""

BING = """
<li class="b_algo">
  <h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=x&amp;u=a1aHR0cHM6Ly9leGFtcGxlLm5ldC90YXJnZXQ&amp;ntb=1">Tracked</a></h2>
  <div class="b_caption"><p>snippet</p></div>
</li>
<li class="b_algo"><h2><a href="/relative">Bad</a></h2></li>
"""

GOOGLE = """
<div class="tF2Cxc">
  <h3>Google hit</h3>
  <a href="/url?q=https%3A%2F%2Fexample.com%2Fg&amp;sa=U">link</a>
  <div class="VwiC3b">google snippet</div>
</div>
"""


def test_parse_duckduckgo_unwraps_and_skips_ads():
    rows = tools_handler.parse_duckduckgo(DDG)
    assert [row["url"] for row in rows] == [
        "https://example.com/a", "https://example.org/b"]
    assert rows[0]["snippet"] == "sa"


def test_parse_bing_unwraps_ck_a_and_skips_relative():
    rows = tools_handler.parse_bing(BING)
    assert [row["url"] for row in rows] == ["https://example.net/target"]
    assert rows[0]["snippet"] == "snippet"


def test_parse_google_unwraps_url_redirect():
    rows = tools_handler.parse_google(GOOGLE)
    assert rows[0]["url"] == "https://example.com/g"
    assert rows[0]["snippet"] == "google snippet"


def test_parse_serpbase_reads_documented_payload():
    rows = tools_handler.parse_serpbase({"organic": [
        {"link": "https://example.com/one", "title": "One",
         "snippet": "s", "position": 3}]})
    assert rows[0]["position"] == 3
    assert rows[0]["engine"] == "serpbase"


def test_safe_slug_cannot_escape_directory():
    assert tools_handler._slug("../../notes") == "notes"
    assert tools_handler._slug("  ") == "query"


def test_language_and_country_normalisation():
    assert tools_handler._normalise_language("en") == "lang_en"
    assert tools_handler._normalise_language("lang_de") == "lang_de"
    assert tools_handler._normalise_country("us") == "countryUS"


class _Response:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            raise httpx.HTTPStatusError(
                "bad", request=httpx.Request("POST", "https://api.example/"),
                response=self)

    def json(self):
        return json.loads(json.dumps(self._payload))


class _Client:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _Client.calls.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, endpoint, json=None, headers=None):
        _Client.calls.append({"endpoint": endpoint, "json": json,
                              "headers": headers})
        return _Response({"organic": [
            {"link": "https://example.com/api", "title": "API"}]})


@pytest.mark.asyncio
async def test_serpbase_posts_json_with_api_key(monkeypatch):
    _Client.calls = []
    monkeypatch.setattr(tools_handler.httpx, "AsyncClient", _Client)
    rows = await tools_handler.fetch_serpbase(
        "acme", "secret", language="en", country="US",
        date_range=("2026-01-01", "2026-02-01"), page=2)
    assert rows[0]["url"] == "https://example.com/api"
    call = _Client.calls[1]
    assert call["endpoint"] == tools_handler.SERPBASE_ENDPOINT
    assert call["json"]["page"] == 2
    assert call["json"]["gl"] == "us"
    assert call["json"]["hl"] == "en"
    assert "after:2026/01/01" in call["json"]["q"]
    assert call["headers"]["X-API-Key"] == "secret"


@pytest.mark.asyncio
async def test_serpbase_requires_key():
    with pytest.raises(tools_handler.SearchError, match="no SerpBase"):
        await tools_handler.fetch_serpbase("acme", "")


@pytest.mark.asyncio
async def test_serpbase_reports_status(monkeypatch):
    class Failing(_Client):
        async def post(self, endpoint, json=None, headers=None):
            return _Response({"status": 401, "error": "invalid key"})

    monkeypatch.setattr(tools_handler.httpx, "AsyncClient", Failing)
    with pytest.raises(tools_handler.SearchError, match="invalid key"):
        await tools_handler.fetch_serpbase("acme", "key")


@pytest.mark.asyncio
async def test_fetch_results_writes_txt_and_json(tmp_path, monkeypatch):
    async def fake(engine, query, **kwargs):
        return [{"engine": engine, "title": "T", "url": "https://example.com/",
                 "snippet": "S", "position": 1}]

    monkeypatch.setattr(tools_handler, "fetch_engine", fake)
    result = await tools_handler.fetch_results(
        "acme", engines=("duckduckgo",), max_results=5, out_dir=tmp_path)
    assert len(result["records"]) == 1
    assert "acme" in result["paths"]["txt"]
    payload = json.loads((tmp_path / "acme.json").read_text(encoding="utf-8"))
    assert payload["total"] == 1
