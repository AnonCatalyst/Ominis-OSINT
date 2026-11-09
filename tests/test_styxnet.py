"""StyxNet client: key loading, normalisation, transport and local limits."""

from __future__ import annotations

import json
import time

import httpx
import pytest

from ominis_src import styxnet


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    monkeypatch.setenv("OMINIS_STYXNET_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv(styxnet.KEY_ENV, raising=False)
    monkeypatch.delenv("OMINIS_STYXNET_KEY", raising=False)
    return tmp_path / "state"


def _write_state(directory, requests=(), lease=None):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "styxnet-usage.json").write_text(
        json.dumps({"requests": list(requests), "lease": lease}),
        encoding="utf-8")


def test_key_precedence_explicit_then_environment_then_file(tmp_path, monkeypatch):
    saved = tmp_path / "styxnet-key.txt"
    saved.write_text("sgn_from_file\n", encoding="utf-8")
    monkeypatch.setattr(styxnet, "key_candidates", lambda: [saved])

    assert styxnet.load_key("sgn_explicit") == "sgn_explicit"
    monkeypatch.setenv(styxnet.KEY_ENV, "sgn_environment")
    assert styxnet.load_key() == "sgn_environment"
    monkeypatch.delenv(styxnet.KEY_ENV)
    monkeypatch.setenv("OMINIS_STYXNET_KEY", "sgn_ominis")
    assert styxnet.load_key() == "sgn_ominis"
    monkeypatch.delenv("OMINIS_STYXNET_KEY")
    assert styxnet.load_key() == "sgn_from_file"


def test_key_file_with_a_bom_is_still_a_key(tmp_path, monkeypatch):
    saved = tmp_path / "styxnet-key.txt"
    saved.write_text("sgn_with_bom\n", encoding="utf-8-sig")
    monkeypatch.setattr(styxnet, "key_candidates", lambda: [saved])
    assert styxnet.load_key() == "sgn_with_bom"


def test_key_source_names_the_source_without_exposing_the_key(
        tmp_path, monkeypatch):
    saved = tmp_path / "styxnet-key.txt"
    saved.write_text("sgn_from_file\n", encoding="utf-8")
    monkeypatch.setattr(styxnet, "key_candidates", lambda: [saved])

    assert styxnet.key_source("sgn_explicit") == (
        "sgn_explicit", "--styxnet-key")
    monkeypatch.setenv(styxnet.KEY_ENV, "sgn_environment")
    assert styxnet.key_source() == (
        "sgn_environment", "STYXNET_ACCESS_KEY (environment)")
    monkeypatch.delenv(styxnet.KEY_ENV)
    monkeypatch.setenv("OMINIS_STYXNET_KEY", "sgn_ominis")
    assert styxnet.key_source() == (
        "sgn_ominis", "OMINIS_STYXNET_KEY (environment)")
    monkeypatch.delenv("OMINIS_STYXNET_KEY")
    assert styxnet.key_source() == ("sgn_from_file", str(saved))


def test_appdata_key_is_a_fallback_after_the_userprofile_file(
        tmp_path, monkeypatch):
    home = tmp_path / "home"
    appdata = tmp_path / "appdata"
    monkeypatch.setattr(styxnet.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("APPDATA", str(appdata))

    appdata_key = appdata / "ominis" / styxnet.KEY_FILE
    appdata_key.parent.mkdir(parents=True)
    appdata_key.write_text("sgn_appdata\n", encoding="utf-8")
    home_key = home / ".config" / "ominis" / styxnet.KEY_FILE

    assert styxnet.key_candidates() == [home_key, appdata_key]
    # The first file is absent, so the APPDATA copy is used.
    assert styxnet.key_source() == ("sgn_appdata", str(appdata_key))

    home_key.parent.mkdir(parents=True)
    home_key.write_text("sgn_home\n", encoding="utf-8")
    assert styxnet.key_source() == ("sgn_home", str(home_key))


def test_key_validation_refuses_an_empty_or_foreign_key():
    with pytest.raises(styxnet.StyxNetError, match="needs a key"):
        styxnet.search("acme", key="")
    with pytest.raises(styxnet.StyxNetError, match="sgn_"):
        styxnet.search("acme", key="secret")


def test_rate_limiter_shares_one_lease_per_machine():
    lease = styxnet._reserve_slot(10)
    try:
        with pytest.raises(styxnet.StyxNetRateLimited, match="already running"):
            styxnet._reserve_slot(10)
    finally:
        styxnet._release_slot(lease)

    # The completed search still counts, so the next one must wait.
    with pytest.raises(styxnet.StyxNetRateLimited, match="cooldown"):
        styxnet._reserve_slot(10)


def test_rate_limiter_allows_the_next_search_after_the_interval(isolated_state):
    _write_state(isolated_state, [time.time() - styxnet.MIN_INTERVAL - 1])
    lease = styxnet._reserve_slot(10)
    styxnet._release_slot(lease)


def test_rate_limiter_enforces_hourly_and_daily_caps(isolated_state):
    now = time.time()
    hourly = [now - 11 - index for index in range(styxnet.MAX_PER_HOUR)]
    _write_state(isolated_state, hourly)
    with pytest.raises(styxnet.StyxNetRateLimited, match="hourly limit"):
        styxnet._reserve_slot(10)

    daily = [now - 900 - index * 240 for index in range(styxnet.MAX_PER_DAY)]
    _write_state(isolated_state, daily)
    with pytest.raises(styxnet.StyxNetRateLimited, match="daily limit"):
        styxnet._reserve_slot(10)


def test_rate_limiter_honours_an_expired_lease(isolated_state):
    _write_state(isolated_state, [], {
        "id": "old", "pid": 1, "expires": time.time() - 1})
    lease = styxnet._reserve_slot(10)
    styxnet._release_slot(lease)


_REAL_CLIENT = httpx.Client


def _client_factory(handler):
    def factory(**kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return _REAL_CLIENT(**kwargs)

    return factory


def test_search_normalises_results_and_filters_dead_profiles(monkeypatch):
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["key"] = request.headers.get("Authorization")
        return httpx.Response(200, json={
            "query": "acme",
            "engines_used": ["duckduckgo", "bing"],
            "elapsed_ms": 42,
            "archive": {"id": "arc-1"},
            "results": [
                {"title": "Acme", "url": "https://acme.example/",
                 "description": "official", "engine": "duckduckgo"},
                {"title": "Broken", "url": "not-a-url"},
                {"title": "Other", "url": "https://other.example/"},
            ],
            "username_results": [
                {"platform": "Nintendo", "url":
                 "https://www.reddit.com/user/acme",
                 "title": "acme (u/acme) - Reddit", "category": "gaming",
                 "confidence": 55},
                {"platform": "Reddit", "url":
                 "https://www.reddit.com/user/generic",
                 "title": "Reddit", "confidence": 55},
                {"platform": "Tumblr", "url":
                 "https://www.tumblr.com/blog/acme",
                 "title": "Register - Login", "confidence": 70},
                {"platform": "OP.GG", "url":
                 "https://op.gg/lol/summoners/search?q=acme",
                 "title": "acme search results", "confidence": 55},
                {"platform": "Gettr", "url": "https://gettr.com/user/acme",
                 "title": "acme on GETTR", "category": "social",
                 "confidence": 90},
                {"platform": "TopCoder", "url":
                 "https://www.topcoder.com/members/acme",
                 "title": "Topcoder", "confidence": 55},
                {"platform": "Niftygateway", "url":
                 "https://niftygateway.com/profile/acme",
                 "title": "acme does not exits on Nifty Gateway"},
                {"platform": "Twitch Clips", "url":
                 "https://www.twitch.tv/acme/clips",
                 "title": "acme Clips - Twitch", "confidence": 55},
                {"platform": "Wattpad", "url":
                 "https://www.wattpad.com/user/acme/videos",
                 "title": "acme videos", "confidence": 55},
                {"platform": "Xbox", "url":
                 "https://www.xbox.com/en-US/play/user/acme",
                 "title": "View acme's profile | Xbox", "confidence": 55},
                {"platform": "X", "url": "https://x.com/acme",
                 "title": "acme (@acme) / X", "confidence": 80},
                {"platform": "Twitter/X", "url": "https://twitter.com/acme",
                 "title": "acme (@acme) / X", "confidence": 100},
                {"platform": "Old", "url": "https://old.example/acme",
                 "title": "Page not found"},
                {"platform": "Gone", "url": "https://gone.example/acme",
                 "status": 404},
                {"platform": "GitHub", "url": "https://github.com/acme",
                 "title": "acme on GitHub", "category": "dev",
                 "confidence": 90},
                {"platform": "GitHub", "url": "https://github.com/acme/",
                 "title": "acme on GitHub"},
            ],
        })

    monkeypatch.setattr(styxnet.httpx, "Client", _client_factory(handler))
    answer = styxnet.search("acme", key="sgn_test", max_engines=12,
                            res_limit=25, scopes=("surface", "onion"))

    assert answer.query == "acme"
    assert answer.engines_used == 2
    assert answer.elapsed_ms == 42
    assert answer.archive_id == "arc-1"
    assert [item["url"] for item in answer.results] == [
        "https://acme.example/", "https://other.example/"]
    assert answer.results[0]["snippet"] == "official"
    # Dead profiles, login walls and search pages are dropped; the channel
    # subpage is canonicalised to the channel; strongest lead first.
    assert [item["platform"] for item in answer.profiles] == [
        "GitHub", "Reddit", "X (Twitter)", "Twitch", "Gettr", "Xbox"]
    by_name = {item["platform"]: item for item in answer.profiles}
    assert by_name["Reddit"]["profile_url"] == (
        "https://www.reddit.com/user/acme")
    assert by_name["Twitch"]["profile_url"] == "https://www.twitch.tv/acme"
    assert by_name["Gettr"]["source"] == "styxnet"
    assert by_name["Gettr"]["confidence"] <= 60
    assert seen["path"].endswith("/search")
    assert seen["key"] == "Bearer sgn_test"
    assert seen["body"]["query"] == "acme"
    assert seen["body"]["scopes"] == ["surface", "onion"]
    assert seen["body"]["max_engines"] == 12
    assert seen["body"]["res_limit"] == 25


def test_search_unescapes_titles_and_accepts_a_numeric_engine_count(monkeypatch):
    def handler(request):
        return httpx.Response(200, json={
            "engines_used": 7,
            "results": [
                {"title": "acme&#x27;s page", "url": "https://acme.example/"},
            ],
        })

    monkeypatch.setattr(styxnet.httpx, "Client", _client_factory(handler))
    answer = styxnet.search("acme", key="sgn_test")
    assert answer.engines_used == 7
    assert answer.results[0]["title"] == "acme's page"


def test_search_surfaces_a_rejected_key(monkeypatch):
    monkeypatch.setattr(styxnet.httpx, "Client", _client_factory(
        lambda request: httpx.Response(401, json={"error": "bad key"})))
    with pytest.raises(styxnet.StyxNetError, match="rejected"):
        styxnet.search("acme", key="sgn_revoked")


def test_search_retries_server_errors_once(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(500, text="trouble")
        return httpx.Response(200, json={"results": []})

    monkeypatch.setattr(styxnet.httpx, "Client", _client_factory(handler))
    monkeypatch.setattr(styxnet.time, "sleep", lambda _: None)
    answer = styxnet.search("acme", key="sgn_test")
    assert answer.results == []
    assert len(calls) == 2


def test_search_rejects_unexpected_payloads(monkeypatch):
    monkeypatch.setattr(styxnet.httpx, "Client", _client_factory(
        lambda request: httpx.Response(200, text="not json")))
    with pytest.raises(styxnet.StyxNetError, match="non-JSON"):
        styxnet.search("acme", key="sgn_test")

    monkeypatch.setattr(styxnet, "MIN_INTERVAL", 0.0)
    monkeypatch.setattr(styxnet.httpx, "Client", _client_factory(
        lambda request: httpx.Response(200, json=[])))
    with pytest.raises(styxnet.StyxNetError, match="unexpected"):
        styxnet.search("acme", key="sgn_test")


@pytest.mark.parametrize("kwargs,message", [
    ({"max_engines": 0}, "max_engines"),
    ({"max_engines": styxnet.MAX_ENGINES + 1}, "max_engines"),
    ({"res_limit": 0}, "res_limit"),
    ({"scopes": ()}, "scope"),
])
def test_search_validates_its_arguments(kwargs, message):
    with pytest.raises(styxnet.StyxNetError, match=message):
        styxnet.search("acme", key="sgn_test", **kwargs)
