"""Search orchestration, de-duplication and report writing."""

import pytest

from ominis_src import config, engines, search


@pytest.fixture(autouse=True)
def _no_page_scan(monkeypatch):
    """Keep the offline search tests offline.

    Page inspection is on by default for real runs. These fakes use reserved
    example URLs, so the scan pass would otherwise hit the network and change
    the record fields the assertions below describe.
    """
    async def skip(*args, **kwargs):
        return {"scanned": 0, "matched": 0, "errors": 0}

    monkeypatch.setattr(search.pagescan, "scan_records", skip)


def _result(url, title="Title", snippet="", engine="duckduckgo", position=1):
    return engines.Result(title=title, url=url, engine=engine,
                          snippet=snippet, position=position)


@pytest.mark.asyncio
async def test_run_collects_deduplicates_and_reports(monkeypatch, tmp_path):
    pages = {
        ("duckduckgo", 1): [_result("https://a.example/"),
                            _result("https://b.example/")],
        ("duckduckgo", 2): [_result("https://c.example/")],
        ("bing", 1): [_result("https://a.example/duplicate", engine="bing"),
                      _result("https://b.example/", engine="bing")],
    }

    async def fake_fetch(engine, settings, page):
        return pages.get((engine, page), [])

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    settings = config.Settings(query="acme", max_results=5,
                               engines=("duckduckgo", "bing"))
    outcome = await search.run(settings)
    # Engines are paginated in lockstep: both page-1 batches arrive before
    # DuckDuckGo's page 2, so a small --max-results is still fed by both.
    assert [record.url for record in outcome.records] == [
        "https://a.example/", "https://b.example/",
        "https://a.example/duplicate", "https://c.example/"]
    assert outcome.proxies_used is False
    assert outcome.errors == []
    assert [record.position for record in outcome.records] == [1, 2, 3, 4]


@pytest.mark.asyncio
async def test_run_keeps_going_when_one_provider_fails(monkeypatch):
    async def fake_fetch(engine, settings, page):
        if engine == "duckduckgo":
            raise engines.EngineError("blocked")
        return [_result("https://b.example/", engine="bing")] if page == 1 else []

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    outcome = await search.run(config.Settings(query="acme"))
    assert len(outcome.records) == 1
    assert outcome.errors == ["duckduckgo: blocked"]


@pytest.mark.asyncio
async def test_serpbase_without_a_key_is_skipped_with_a_message(monkeypatch):
    called = []

    async def fake_fetch(engine, settings, page):
        called.append(engine)
        return []

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    outcome = await search.run(config.Settings(
        query="acme", engines=("serpbase", "bing")))
    assert called == ["bing"]
    assert outcome.errors and "no API key" in outcome.errors[0]


@pytest.mark.asyncio
async def test_run_honours_max_results(monkeypatch):
    async def fake_fetch(engine, settings, page):
        if page > 1:
            return []
        return [_result(f"https://{index}.example/") for index in range(10)]

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    outcome = await search.run(config.Settings(query="acme", max_results=3))
    assert len(outcome.records) == 3


@pytest.mark.asyncio
async def test_progress_sees_each_new_record(monkeypatch):
    async def fake_fetch(engine, settings, page):
        return [_result("https://a.example/"),
                _result("https://b.example/")] if page == 1 else []

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    seen = []
    await search.run(config.Settings(query="acme"), seen.append)
    assert [item.url for item in seen] == [
        "https://a.example/", "https://b.example/"]


@pytest.mark.asyncio
async def test_mentions_are_counted_across_title_url_and_snippet(monkeypatch):
    async def fake_fetch(engine, settings, page):
        if page > 1:
            return []
        return [_result("https://acme.example/", title="About Acme",
                        snippet="acme and ACME again")]

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    outcome = await search.run(config.Settings(query="acme"))
    assert outcome.mentions["acme"] == 4


@pytest.mark.asyncio
async def test_profiles_are_collected_once(monkeypatch):
    async def fake_fetch(engine, settings, page):
        if page > 1:
            return []
        return [_result("https://github.com/acme"),
                _result("https://www.instagram.com/acme")]

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    outcome = await search.run(config.Settings(query="acme"))
    platforms = {profile["platform"] for profile in outcome.profiles}
    assert {"GitHub", "Instagram"}.issubset(platforms)
    assert len(outcome.profiles) == len({p["profile_url"] for p in outcome.profiles})


@pytest.mark.asyncio
async def test_unscanned_records_still_carry_profile_depth(monkeypatch):
    async def fake_fetch(engine, settings, page):
        if page > 1:
            return []
        return [_result("https://github.com/acme")]

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    outcome = await search.run(config.Settings(query="acme"))
    record = outcome.records[0]
    assert record.scanned is False
    assert record.platform == "GitHub"
    assert record.category == "dev"
    assert record.confidence == 90
    assert record.handle == "acme"
    profile = outcome.profiles[0]
    assert profile["handle"] == "acme"
    assert profile["category"] == "dev"
    assert profile["confidence"] == 90
    detection = outcome.detections()
    assert detection["handles"] == ["acme"]
    assert detection["categories"] == {"dev": 1}


@pytest.mark.asyncio
async def test_styxnet_replaces_the_local_engines(monkeypatch):
    async def must_not_run(engine, settings, page):
        raise AssertionError("local engines should not run")

    def fake_styxnet(query, **kwargs):
        assert kwargs["key"] == "sgn_test"
        assert kwargs["max_engines"] == 9
        return search.styxnet.StyxNetAnswer(
            query=query,
            results=[{"title": "Acme", "url": "https://acme.example/",
                      "snippet": "official", "engine": "duckduckgo"}],
            profiles=[{"platform": "GitHub", "profile_url":
                       "https://github.com/acme", "category": "dev",
                       "confidence": 90, "source": "styxnet"}],
            engines_used=25, elapsed_ms=1200, archive_id="arc-1")

    monkeypatch.setattr(engines, "fetch_engine", must_not_run)
    monkeypatch.setattr(search.styxnet, "search", fake_styxnet)
    outcome = await search.run(config.Settings(
        query="acme", styxnet=True, styxnet_key="sgn_test",
        styxnet_engines=9))

    assert outcome.styxnet is True
    assert outcome.engines == ["styxnet"]
    assert [record.url for record in outcome.records] == ["https://acme.example/"]
    assert outcome.records[0].engine == "styxnet"
    assert outcome.styxnet_meta == {"engines": 25, "elapsed_ms": 1200,
                                    "archive_id": "arc-1"}
    assert outcome.profiles[0]["platform"] == "GitHub"
    assert outcome.errors == []


@pytest.mark.asyncio
async def test_styxnet_profiles_deduplicate_against_result_detection(monkeypatch):
    def fake_styxnet(query, **kwargs):
        return search.styxnet.StyxNetAnswer(
            query=query,
            results=[{"title": "acme", "url": "https://x.com/acme",
                      "snippet": "", "engine": "styxnet"}],
            profiles=[{"platform": "X (Twitter)", "profile_url":
                       "https://twitter.com/acme/", "category": "social",
                       "confidence": 80, "source": "styxnet"}],
            engines_used=3)

    monkeypatch.setattr(search.styxnet, "search", fake_styxnet)
    outcome = await search.run(config.Settings(
        query="acme", styxnet=True, styxnet_key="sgn_test"))

    assert len(outcome.profiles) == 1
    assert outcome.profiles[0]["profile_url"] == "https://twitter.com/acme/"


@pytest.mark.asyncio
async def test_styxnet_failure_falls_back_to_local_search(monkeypatch):
    async def fake_fetch(engine, settings, page):
        return [_result("https://local.example/")] if page == 1 else []

    def fake_styxnet(query, **kwargs):
        raise search.styxnet.StyxNetRateLimited("wait", 8)

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    monkeypatch.setattr(search.styxnet, "search", fake_styxnet)
    outcome = await search.run(config.Settings(
        query="acme", styxnet=True, styxnet_key="sgn_test"))

    assert outcome.styxnet is False
    assert [record.url for record in outcome.records] == ["https://local.example/"]
    assert outcome.errors and "styxnet" in outcome.errors[0].lower()


@pytest.mark.asyncio
async def test_write_uses_the_configured_formats(monkeypatch, tmp_path):
    async def fake_fetch(engine, settings, page):
        return [_result("https://a.example/")] if page == 1 else []

    monkeypatch.setattr(engines, "fetch_engine", fake_fetch)
    settings = config.Settings(query="acme", formats=("txt", "md"),
                               out_dir=tmp_path)
    outcome = await search.run(settings)
    written = search.write(outcome, settings)
    assert set(written) == {"txt", "md"}
    for path in written.values():
        assert tmp_path in __import__("pathlib").Path(path).parents
