"""Settings, environment parsing and proxy files."""

import os
from pathlib import Path

import pytest

from ominis_src import config


def test_defaults_keep_proxies_off():
    settings = config.Settings(query="acme")
    assert settings.proxies == ()
    assert settings.proxy_enabled is False
    assert settings.engines == ("duckduckgo", "bing")
    assert settings.formats == ("txt", "json")
    assert settings.verify_tls is True


@pytest.mark.parametrize("value,expected", [
    ("", ("duckduckgo", "bing")),
    (None, ("duckduckgo", "bing")),
    ("duckduckgo", ("duckduckgo",)),
    ("duckduckgo, bing", ("duckduckgo", "bing")),
    ("duckduckgo,serpbase", ("duckduckgo", "serpbase")),
])
def test_parse_engines(value, expected):
    assert config.parse_engines(value) == expected


def test_parse_engines_rejects_unknown_names():
    with pytest.raises(ValueError, match="unknown engine"):
        config.parse_engines("google")


@pytest.mark.parametrize("value,expected", [
    ("", ""),
    (None, ""),
    ("2026-01-31", "2026-01-31"),
])
def test_parse_date(value, expected):
    assert config.parse_date(value) == expected


@pytest.mark.parametrize("value", ["31-01-2026", "2026-13-01", "yesterday"])
def test_parse_date_rejects_other_formats(value):
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        config.parse_date(value)


def test_settings_validate_ranges():
    with pytest.raises(ValueError, match="query"):
        config.Settings(query="   ")
    with pytest.raises(ValueError, match="max_results"):
        config.Settings(query="acme", max_results=0)
    with pytest.raises(ValueError, match="timeout"):
        config.Settings(query="acme", timeout=0)
    with pytest.raises(ValueError, match="output format"):
        config.Settings(query="acme", formats=("xml",))


def test_settings_page_size_is_bounded():
    assert config.Settings(query="acme", max_results=1).page_size == 10
    assert config.Settings(query="acme", max_results=1000).page_size == 200


def test_from_env_reads_omins_variables(monkeypatch):
    monkeypatch.setenv("OMINIS_ENGINES", "bing,serpbase")
    monkeypatch.setenv("OMINIS_LANGUAGE", "en")
    monkeypatch.setenv("OMINIS_COUNTRY", "US")
    monkeypatch.setenv("OMINIS_SINCE", "2026-01-01")
    monkeypatch.setenv("OMINIS_MAX_RESULTS", "25")
    monkeypatch.setenv("OMINIS_PROXY_POOL", "127.0.0.1:8080, socks5://127.0.0.1:1080 ")
    monkeypatch.setenv("SERPBASE_API_KEY", "key-from-env")
    monkeypatch.setenv("OMINIS_FORMATS", "json,md")
    monkeypatch.setenv("OMINIS_TIMEOUT", "5")
    settings = config.Settings.from_env("acme")
    assert settings.engines == ("bing", "serpbase")
    assert settings.language == "en"
    assert settings.country == "US"
    assert settings.since == "2026-01-01"
    assert settings.max_results == 25
    assert settings.proxies == ("127.0.0.1:8080", "socks5://127.0.0.1:1080")
    assert settings.serpbase_key == "key-from-env"
    assert settings.formats == ("json", "md")
    assert settings.timeout == 5.0


def test_from_env_ignores_empty_overrides(monkeypatch):
    monkeypatch.setenv("OMINIS_ENGINES", "bing")
    settings = config.Settings.from_env("acme", engines=None, language="de")
    assert settings.engines == ("bing",)
    assert settings.language == "de"


def test_load_proxy_file_skips_comments_and_blanks(tmp_path):
    path = tmp_path / "proxies.txt"
    path.write_text("# comment\n\n127.0.0.1:8080\n  socks5://127.0.0.1:1080  # inline\n",
                    encoding="utf-8")
    assert config.load_proxy_file(path) == (
        "127.0.0.1:8080", "socks5://127.0.0.1:1080")


def test_load_proxy_file_requires_a_file(tmp_path):
    with pytest.raises(ValueError, match="no proxy file"):
        config.load_proxy_file(tmp_path / "missing.txt")
