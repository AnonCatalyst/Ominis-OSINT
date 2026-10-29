"""Shared helpers: mentions, profiles and Bing redirects."""

import pytest

from ominis_src import utils


def test_unwrap_bing_click_tracker():
    url = ("https://www.bing.com/ck/a?!&&p=abc&u="
           "a1aHR0cHM6Ly9leGFtcGxlLm5ldC90YXJnZXQ&ntb=1")
    assert utils.unwrap_bing_url(url) == "https://example.net/target"


@pytest.mark.parametrize("url,expected", [
    ("/l/?uddg=https%3A%2F%2Fexample.com%2Fone&rut=abc",
     "https://example.com/one"),
    ("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Ftwo",
     "https://example.com/two"),
    ("https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fthree",
     "https://example.com/three"),
    ("https://example.com/direct", "https://example.com/direct"),
    ("//example.com/direct", "//example.com/direct"),
    ("", ""),
    (None, None),
])
def test_unwrap_duckduckgo_redirects(url, expected):
    assert utils.unwrap_duckduckgo_url(url) == expected


@pytest.mark.parametrize("url", [
    "https://example.com/page",
    "https://bing.com/search?q=acme",
    "https://www.bing.com/ck/a?u=not-base64",
    "https://www.bing.com/ck/a?u=a1!!!",
    "https://www.bing.com/ck/a?u=a1bm90LWEtdXJs",
    None,
    123,
])
def test_unwrap_bing_leaves_other_urls_alone(url):
    assert utils.unwrap_bing_url(url) == url


def test_find_social_profiles_is_repeatable():
    first = utils.find_social_profiles("https://github.com/acme")
    second = utils.find_social_profiles("https://github.com/acme")
    assert first == second
    assert first[0]["platform"] == "GitHub"


def test_potential_forum_without_a_hostname_does_not_crash():
    assert utils.is_potential_forum("not a url") is False
    assert utils.is_potential_forum("https://forum.example/thread") is True
    assert utils.is_potential_forum("https://community.example/") is True


def test_extract_mentions_counts_case_insensitively():
    assert utils.extract_mentions("Acme and ACME and other", "acme") == {"acme": 2}
    assert utils.extract_mentions("acme", ["acme", "other"]) == {"acme": 1, "other": 0}


def test_extract_mentions_rejects_empty_text():
    with pytest.raises(ValueError, match="non-empty"):
        utils.extract_mentions("", "acme")
