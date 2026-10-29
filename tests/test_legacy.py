"""Offline tests for the legacy 0.5.x build."""

import json

import pytest

from ominis_src import tools_handler, usr, utils


DDG = """
<div class="result">
  <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">A</a>
  <a class="result__snippet">sa</a>
</div>
<div class="result"><a class="result__a" href="https://duckduckgo.com/y.js?ad=1">ad</a></div>
"""

BING = """
<li class="b_algo">
  <h2><a href="https://www.bing.com/ck/a?!&amp;&amp;u=a1aHR0cHM6Ly9leGFtcGxlLm5ldC90YXJnZXQ&amp;ntb=1">Tracked</a></h2>
  <p>snippet</p>
</li>
"""


def test_ddg_unwrap_and_ad_filter():
    rows = tools_handler.parse_duckduckgo(DDG)
    assert [row["url"] for row in rows] == ["https://example.com/a"]


def test_bing_unwrap():
    rows = tools_handler.parse_bing(BING)
    assert [row["url"] for row in rows] == ["https://example.net/target"]


def test_look_alike_hosts_are_not_unwrapped():
    assert tools_handler._unwrap_ddg(
        "https://duckduckgo.com.example.net/l/?uddg=https%3A%2F%2Fevil") == (
        "https://duckduckgo.com.example.net/l/?uddg=https%3A%2F%2Fevil")
    assert tools_handler._unwrap_bing(
        "https://bing.com.example.net/ck/a?u=a1aHR0cHM6Ly9ldmls") == (
        "https://bing.com.example.net/ck/a?u=a1aHR0cHM6Ly9ldmls")
    assert tools_handler._host_matches("https://evilduckduckgo.com/",
                                       "duckduckgo.com") is False
    assert tools_handler._host_matches("https://html.duckduckgo.com/",
                                       "duckduckgo.com") is True


def test_serpbase_parse_documented_payload():
    rows = tools_handler.parse_serpbase({"organic": [
        {"link": "https://example.com/one", "title": "One", "position": 2}]})
    assert rows[0]["position"] == 2
    assert rows[0]["engine"] == "serpbase"


def test_safe_output_name():
    assert tools_handler._slug("../../notes") == "notes"
    assert tools_handler._slug("  ") == "query"


def test_forum_helper_survives_missing_hostname():
    assert utils.is_potential_forum("https:///forum") is True
    assert utils.is_potential_forum("mailto:someone@example.com") is False


def test_username_url_shapes():
    assert usr._profile_url("https://example.com/", "acme") == "https://example.com/acme"
    assert usr._profile_url("https://example.com/@", "acme") == "https://example.com/@acme"
    assert usr._profile_url("https://example.com/user?u=", "acme") == "https://example.com/user?u=acme"
    assert usr._profile_url("https://example.com/u/{username}", "acme") == "https://example.com/u/acme"


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
async def test_serpbase_posts_json(monkeypatch):
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
    assert "before:2026/02/01" in call["json"]["q"]
    assert call["headers"]["X-API-Key"] == "secret"


@pytest.mark.asyncio
async def test_serpbase_reports_api_status(monkeypatch):
    class Failing(_Client):
        async def post(self, endpoint, json=None, headers=None):
            return _Response({"status": 401, "error": "invalid key"})

    monkeypatch.setattr(tools_handler.httpx, "AsyncClient", Failing)
    with pytest.raises(tools_handler.SearchError, match="invalid key"):
        await tools_handler.fetch_serpbase("acme", "key")


@pytest.mark.asyncio
async def test_fetch_writes_safe_report(tmp_path, monkeypatch):
    async def fake(engine, query, start=0, proxies=None, **kwargs):
        return [{"engine": engine, "title": "T", "url": "https://example.com/",
                 "snippet": "S", "position": 1}]

    monkeypatch.setattr(tools_handler, "fetch_engine_results", fake)
    total, mentions, profiles = await tools_handler.fetch_dual_engine_results(
        "../../notes", max_results=1, proxies=(), out_dir=tmp_path)
    assert total == 1
    assert (tmp_path / "notes_dual-engine_results.txt").exists()
    assert (tmp_path / "notes_dual-engine_results.json").exists()
