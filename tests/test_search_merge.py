"""Regression tests for profile evidence merging."""

from ominis_src import report, search


def test_known_profile_inherits_confirmed_page_evidence():
    known = [{
        "platform": "GitHub",
        "profile_url": "https://github.com/acme",
        "category": "dev",
        "confidence": 75,
        "handle": "acme",
        "source": "styxnet",
    }]
    record = report.SearchRecord(
        title="acme",
        url="https://github.com/acme",
        platform="GitHub",
        category="dev",
        confidence=80,
        handle="acme",
        final_url="https://github.com/acme",
        signal="metadata",
        matched=True,
        scanned=True,
        status=200,
        page_title="acme",
    )
    profiles = search._profiles(known, [record])
    assert len(profiles) == 1
    profile = profiles[0]
    assert profile["verified"] is True
    assert profile["page_signal"] == "metadata"
    assert profile["confidence"] >= 92
    assert profile["profile_url"] == "https://github.com/acme"
