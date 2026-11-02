"""Platform detection: precise entries, the wide table and forum checks."""

import pytest

from ominis_src import platforms, utils


@pytest.mark.parametrize("url,platform,category", [
    ("https://github.com/acme", "GitHub", "dev"),
    ("https://www.github.com/acme", "GitHub", "dev"),
    ("https://x.com/acme", "X (Twitter)", "social"),
    ("https://twitter.com/acme", "X (Twitter)", "social"),
    ("https://reddit.com/user/acme", "Reddit", "forum"),
    ("https://www.instagram.com/acme", "Instagram", "social"),
    ("https://linkedin.com/in/acme", "LinkedIn", "professional"),
    ("https://youtube.com/@acme", "YouTube", "video"),
    ("https://twitch.tv/acme", "Twitch", "video"),
    ("https://t.me/acme", "Telegram", "messaging"),
    ("https://wa.me/15551234567", "WhatsApp", "messaging"),
    ("https://ok.ru/profile/123", "OK.ru", "social"),
    ("https://wikipedia.org/wiki/user:acme", "Wikipedia", "research"),
])
def test_precise_profiles_are_detected(url, platform, category):
    found = platforms.detect_profiles(url)
    assert len(found) == 1
    assert found[0]["platform"] == platform
    assert found[0]["category"] == category
    assert found[0]["profile_url"].startswith("https://")


@pytest.mark.parametrize("url", [
    "https://github.com/features",
    "https://github.com/acme/repo",
    "https://reddit.com/user/acme/comments/xyz",
    "https://instagram.com/explore",
    "https://instagram.com/p",
    "https://x.com/home",
    "https://x.com/p",
    "https://example.com/",
    "not a url",
    "",
    None,
])
def test_non_profile_urls_are_not_detected(url):
    assert platforms.detect_profiles(url) == []


def test_bare_p_path_is_not_a_profile_on_any_platform():
    # ``/p`` is a post/content prefix nearly everywhere; a bare one is never
    # a handle, including in the wide original table.
    for platform in platforms.PLATFORMS:
        for host in platform.hosts:
            assert platforms.detect_profiles(f"https://{host}/p") == []
    assert platforms.detect_profiles("https://guru.com/p") == []


def test_subdomain_platforms_ignore_the_site_itself():
    assert platforms.detect_profiles("https://acme.bandcamp.com/album/one")[0][
        "platform"] == "Bandcamp"
    assert platforms.detect_profiles("https://www.bandcamp.com/album/one") == []
    assert platforms.detect_profiles("https://bandcamp.com/album/one") == []


def test_wide_original_table_still_detects_its_platforms():
    # ``guru.com/<handle>`` only exists in the original wide table.
    found = platforms.detect_profiles("https://guru.com/acme")
    assert found[0]["platform"] == "Guru"
    assert found[0]["category"] == "marketplace"
    assert found[0]["confidence"] == 45


def test_wide_table_strips_www_before_matching():
    found = platforms.detect_profiles("https://www.guru.com/acme")
    assert found[0]["platform"] == "Guru"
    assert found[0]["profile_url"] == "https://guru.com/acme"


def test_wide_table_rejects_section_words_and_deep_links():
    assert platforms.detect_profiles("https://guru.com/about") == []
    assert platforms.detect_profiles("https://guru.com/acme/portfolio") == []


@pytest.mark.parametrize("url,label", [
    ("https://bionluk.com/acme", "Bionluk"),
    ("https://ws2.kik.com/user/acme", "Kik"),
    ("https://users.scala-lang.org/u/acme", "Scala Lang"),
    ("https://www.photo.net/photodb/user?acme", "Photo"),
    ("https://example.com/", "Example"),
    ("not a url", ""),
    ("https://localhost/", ""),
])
def test_host_label_for_unregistered_sites(url, label):
    assert platforms.host_label(url) == label


@pytest.mark.parametrize("left,right,equal", [
    ("https://x.com/acme", "https://twitter.com/acme/", True),
    ("https://www.paypal.me/acme", "https://paypal.me/acme", True),
    ("https://github.com/acme", "https://github.com/acme/", True),
    ("https://github.com/acme", "https://github.com/other", False),
    ("https://x.com/acme", "https://x.com/other", False),
    ("https://www.yelp.com/user_details?userid=acme",
     "https://www.yelp.com/user_details?userid=other", False),
])
def test_profile_key_normalises_aliases(left, right, equal):
    assert (platforms.profile_key({"profile_url": left})
            == platforms.profile_key({"profile_url": right})) is equal


def test_platform_counts_cover_both_tables():
    assert platforms.extended_platform_count() >= 100
    assert platforms.platform_count() > platforms.extended_platform_count()


@pytest.mark.parametrize("url,expected", [
    ("https://forum.example/thread", True),
    ("https://community.example/", True),
    ("https://discourse.example/t/topic/1", True),
    ("https://example.com/forums/", True),
    ("https://pornhub.com", False),
    ("https://github.com/acme", False),
    ("https://hub.example.com/", False),
    ("https://example.com/discussion", True),
    ("not a url", False),
    (None, False),
])
def test_forum_detection_uses_whole_words(url, expected):
    assert platforms.is_forum_url(url) is expected


def test_discourse_and_fediverse_fallbacks():
    discourse = platforms.detect_profiles("https://example.com/u/acme")
    assert discourse[0]["platform"] == "Discourse forum"
    assert discourse[0]["profile_url"] == "https://example.com/u/acme"

    fediverse = platforms.detect_profiles("https://social.example/@acme")
    assert fediverse[0]["platform"] == "Fediverse (Mastodon-compatible)"


@pytest.mark.parametrize("url,platform,expected", [
    ("https://youtube.com/@acme/posts", "YouTube",
     "https://youtube.com/@acme"),
    ("https://www.youtube.com/@acme/videos", "YouTube",
     "https://www.youtube.com/@acme"),
    ("https://twitch.tv/acme/clips", "Twitch", "https://twitch.tv/acme"),
    ("https://www.twitch.tv/acme/about", "Twitch",
     "https://www.twitch.tv/acme"),
])
def test_channel_subpages_canonicalise_to_the_parent_profile(
        url, platform, expected):
    found = platforms.detect_profiles(url)
    assert found[0]["platform"] == platform
    assert found[0]["profile_url"] == expected


def test_known_hosts_do_not_fall_back_to_a_generic_forum():
    # ``github.com/community/thread`` looks like a forum by path word, but the
    # host is already known, so the generic fallback must stay out of the way.
    assert utils.find_social_profiles("https://github.com/community/thread") == []
    youtube = utils.find_social_profiles("https://youtube.com/@acme/posts")
    assert youtube[0]["platform"] == "YouTube"


def test_profile_key_ignores_tracking_parameters():
    left = platforms.profile_key({
        "profile_url": "https://github.com/acme?utm_source=newsletter"})
    right = platforms.profile_key({"profile_url": "https://github.com/acme"})
    assert left == right


def test_utils_delegates_and_keeps_the_original_shape():
    profiles = utils.find_social_profiles("https://github.com/acme")
    assert profiles[0]["platform"] == "GitHub"
    assert profiles[0]["profile_url"] == "https://github.com/acme"
    assert profiles[0]["category"] == "dev"

    # A URL that is a forum but not a named profile still gets one record.
    forums = utils.find_social_profiles("https://forum.example/thread/1")
    assert forums[0]["platform"] == "Forum"
    assert forums[0]["category"] == "forum"
