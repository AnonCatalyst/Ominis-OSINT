"""Search orchestration, de-duplication and report writing."""

import pytest

from ominis_src import config, engines, search


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
    assert [record.url for record in outcome.records] == [
        "https://a.example/", "https://b.example/", "https://c.example/",
        "https://a.example/duplicate"]
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
