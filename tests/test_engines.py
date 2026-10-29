"""Engine URLs, parsers and the optional results API."""

import json

import pytest

from ominis_src import config, engines, tools_handler


DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="/l/?uddg=https%3A%2F%2Fexample.com%2Fone&amp;rut=abc">First hit</a>
  <a class="result__snippet">A first <b>snippet</b></a>
</div>
<div class="result">
  <a class="result__a" href="https://example.org/two">Second hit</a>
  <div class="result__snippet">Another snippet</div>
</div>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fthree&amp;rut=def">Third hit</a>
  <div class="result__snippet">Third snippet</div>
</div>
<div class="result">
  <a class="result__a" href="https://duckduckgo.com/y.js?ad_domain=shop.example&ad_provider=bingv7aa">An ad</a>
  <div class="result__snippet">Bought placement</div>
</div>
<div class="result"><a class="result__a" href="javascript:void(0)">Bogus</a></div>
</body></html>
"""

BING_HTML = """
<html><body>
<li class="b_algo">
  <h2><a href="https://example.com/bing-one">Bing one</a></h2>
  <div class="b_caption"><p>Bing snippet one</p></div>
</li>
<li class="b_algo">
  <h2><a href="/relative">Relative</a></h2>
</li>
<li class="b_algo">
  <h2><a href="https://www.bing.com/ck/a?!&amp;&amp;p=abc&amp;u=a1aHR0cHM6Ly9leGFtcGxlLm5ldC90YXJnZXQ&amp;ntb=1">Tracked</a></h2>
</li>
</body></html>
"""


def test_duckduckgo_url_carries_filters():
    url = engines.duckduckgo_url("acme corp", page=20, language="en",
                                 country="US", since="2026-01-01",
                                 until="2026-02-01")
    assert url.startswith("https://html.duckduckgo.com/html/?")
    assert "q=acme+corp" in url
    assert "s=20" in url
    assert "kl=us-en" in url
    assert "df=2026-01-01..2026-02-01" in url


def test_bing_url_carries_filters():
    url = engines.bing_url("acme corp", page=11, language="de", country="DE",
                           since="2026-01-01", until="2026-02-01")
    assert url.startswith("https://www.bing.com/search?")
    assert "q=acme+corp" in url
    assert "first=11" in url
    assert "cc=DE" in url
    assert "setlang=de" in url
    assert "ez5_2026-01-01_2026-02-01" in url


def test_parse_duckduckgo_unwraps_redirects_and_skips_non_http():
    results = engines.parse_duckduckgo(DDG_HTML)
    assert [item.url for item in results] == [
        "https://example.com/one", "https://example.org/two",
        "https://example.com/three"]
    assert results[0].title == "First hit"
    assert results[0].snippet == "A first snippet"
    assert [item.position for item in results] == [1, 2, 3]
    assert all(item.engine == "duckduckgo" for item in results)


def test_parse_bing_reads_heading_and_caption():
    results = engines.parse_bing(BING_HTML)
    assert [item.url for item in results] == [
        "https://example.com/bing-one", "https://example.net/target"]
    assert results[0].title == "Bing one"
    assert results[0].snippet == "Bing snippet one"
    assert results[0].engine == "bing"
    assert results[1].title == "Tracked"


@pytest.mark.parametrize("payload,expected", [
    ({"results": [{"url": "https://a.example/", "title": "A",
                   "snippet": "sa", "position": 4}]}, 1),
    ({"organic": [{"link": "https://b.example/", "name": "B"}]}, 1),
    ({"organic_results": [{"link": "https://b2.example/", "name": "B2"}]}, 1),
    ({"data": {"organic_results": [{"href": "https://c.example/"}]}}, 1),
    ([{"url": "https://d.example/"}, {"url": "not-a-url"}], 1),
    ({"results": [{"url": "https://e.example/", "description": "de"}]}, 1),
    ({"results": []}, 0),
    ({"unexpected": []}, 0),
])
def test_parse_serpbase_accepts_common_envelopes(payload, expected):
    results = engines.parse_serpbase(payload)
    assert len(results) == expected
    if results:
        assert results[0].engine == "serpbase"


def test_parse_serpbase_keeps_api_position_and_description():
    results = engines.parse_serpbase({"results": [{
        "url": "https://a.example/", "title": "A", "description": "text",
        "position": 7}]})
    assert results[0].position == 7
    assert results[0].snippet == "text"


@pytest.mark.asyncio
async def test_fetch_engine_uses_scraped_transport(monkeypatch):
    seen = {}

    async def fake_request(url, proxies=None):
        seen["url"] = url
        seen["proxies"] = proxies
        return DDG_HTML

    monkeypatch.setattr(tools_handler, "make_request_async", fake_request)
    settings = config.Settings(query="acme", engines=("duckduckgo",))
    results = await engines.fetch_engine("duckduckgo", settings, page=2)
    assert "s=10" in seen["url"]
    assert seen["proxies"] is None
    assert len(results) == 3


@pytest.mark.asyncio
async def test_fetch_engine_passes_an_explicit_pool(monkeypatch):
    seen = {}

    async def fake_request(url, proxies=None):
        seen["proxies"] = proxies
        return BING_HTML

    monkeypatch.setattr(tools_handler, "make_request_async", fake_request)
    settings = config.Settings(query="acme", engines=("bing",),
                               proxies=("127.0.0.1:8080",))
    await engines.fetch_engine("bing", settings, page=1)
    assert seen["proxies"] == ("127.0.0.1:8080",)


@pytest.mark.asyncio
async def test_fetch_engine_rejects_unknown_provider():
    settings = config.Settings(query="acme")
    with pytest.raises(engines.EngineError, match="unknown engine"):
        await engines.fetch_engine("google", settings, page=1)


@pytest.mark.asyncio
async def test_fetch_serpbase_requires_a_key():
    with pytest.raises(engines.EngineError, match="no SerpBase API key"):
        await engines.fetch_serpbase("acme", "")


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise __import__("httpx").HTTPStatusError(
                "bad", request=__import__("httpx").Request("GET", "https://api.example/"),
                response=self)

    def json(self):
        return json.loads(json.dumps(self._payload))


class _FakeClient:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _FakeClient.calls.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, endpoint, json=None, headers=None):
        _FakeClient.calls.append({"endpoint": endpoint, "json": json,
                                  "headers": headers})
        return _FakeResponse({"organic": [
            {"link": "https://google.example/", "title": "G",
             "snippet": "gs", "position": 1}]})


@pytest.mark.asyncio
async def test_fetch_serpbase_builds_a_google_request(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.setattr(engines.httpx, "AsyncClient", _FakeClient)
    results = await engines.fetch_serpbase(
        "acme", "secret-key", language="en", country="US",
        since="2026-01-01", until="2026-02-01", page=2, per_page=10,
        timeout=7.0, verify_tls=False)
    assert results[0].url == "https://google.example/"
    assert results[0].snippet == "gs"
    client_kwargs = _FakeClient.calls[0]
    assert client_kwargs["timeout"] == 7.0
    assert client_kwargs["verify"] is False
    assert client_kwargs["proxy"] is None
    call = _FakeClient.calls[1]
    assert call["endpoint"] == config.SERPBASE_ENDPOINT
    assert call["json"]["page"] == 2
    assert call["json"]["gl"] == "us"
    assert call["json"]["hl"] == "en"
    assert "after:2026/01/01" in call["json"]["q"]
    assert "before:2026/02/01" in call["json"]["q"]
    assert call["headers"]["X-API-Key"] == "secret-key"
    assert call["headers"]["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_fetch_serpbase_omits_empty_filters(monkeypatch):
    _FakeClient.calls = []
    monkeypatch.setattr(engines.httpx, "AsyncClient", _FakeClient)
    await engines.fetch_serpbase("acme", "key")
    body = _FakeClient.calls[1]["json"]
    assert body == {"q": "acme", "page": 1}


@pytest.mark.asyncio
async def test_fetch_serpbase_reports_api_status(monkeypatch):
    class Failing(_FakeClient):
        async def post(self, endpoint, json=None, headers=None):
            return _FakeResponse({"status": 401, "error": "invalid key"})

    monkeypatch.setattr(engines.httpx, "AsyncClient", Failing)
    with pytest.raises(engines.EngineError, match="invalid key"):
        await engines.fetch_serpbase("acme", "key")


@pytest.mark.asyncio
async def test_fetch_serpbase_reports_http_errors(monkeypatch):
    class Bad(_FakeClient):
        async def post(self, endpoint, json=None, headers=None):
            return _FakeResponse({}, status=503)

    monkeypatch.setattr(engines.httpx, "AsyncClient", Bad)
    with pytest.raises(engines.EngineError, match="HTTP 503"):
        await engines.fetch_serpbase("acme", "key")


@pytest.mark.asyncio
async def test_fetch_serpbase_wraps_transport_errors(monkeypatch):
    class Broken(_FakeClient):
        async def post(self, endpoint, json=None, headers=None):
            raise __import__("httpx").ConnectError("no route")

    monkeypatch.setattr(engines.httpx, "AsyncClient", Broken)
    with pytest.raises(engines.EngineError, match="SerpBase request failed"):
        await engines.fetch_serpbase("acme", "key")
