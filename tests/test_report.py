"""Result file names and writers."""

import csv
import json

import pytest

from ominis_src import report


@pytest.mark.parametrize("query,expected", [
    ("acme", "acme"),
    ("Acme Corp", "Acme-Corp"),
    ("../../etc/passwd", "etc-passwd"),
    ("what?", "what"),
    ("", "results"),
    ("...", "results"),
    ("CON", "results-CON"),
    ("lpt1.txt", "results-lpt1.txt"),
    ('a/b\\c:d*e?f"g<h>i|j', "a-b-c-d-e-f-g-h-i-j"),
])
def test_slug_is_safe(query, expected):
    assert report.slug(query) == expected


def test_slug_is_bounded():
    assert len(report.slug("x" * 500)) <= 60
    assert report.slug("x" * 500).strip("-. ") == report.slug("x" * 500)


def test_results_path_uses_extension_for_formats(tmp_path):
    assert report.results_path(tmp_path, "Acme Corp", "txt") == tmp_path / "Acme-Corp.txt"
    assert (report.results_path(tmp_path, "Acme Corp", "dual-engine_results.txt")
            == tmp_path / "Acme-Corp-dual-engine_results.txt")
    assert report.results_path(tmp_path, "acme", "") == tmp_path / "acme"


def _sample_report():
    return report.SearchReport(
        query="Acme Corp",
        records=[
            report.SearchRecord(title="One", url="https://one.example/",
                                engine="duckduckgo", snippet="first", position=1,
                                scanned=True, matched=True, signal="metadata",
                                platform="GitHub", category="dev",
                                confidence=90, handle="acme"),
            report.SearchRecord(title="Two", url="https://two.example/",
                                engine="bing", snippet="second", position=2,
                                scanned=True, matched=False, signal="url",
                                platform="GitHub", category="dev",
                                confidence=90, handle="other"),
        ],
        mentions={"acme": 3},
        profiles=[{"platform": "GitHub", "profile_url": "github.com/acme",
                   "category": "dev", "confidence": 92, "handle": "acme",
                   "source": "metadata", "verified": True}],
        engines=["duckduckgo", "bing"],
        errors=["bing: timed out"],
    )


def test_write_all_creates_every_format(tmp_path):
    written = report.write_all(_sample_report(), tmp_path, ("txt", "json", "csv", "md"))
    assert set(written) == {"txt", "json", "csv", "md"}
    for path in written.values():
        assert path.is_file()
        assert path.name.startswith("Acme-Corp")
    assert written["txt"].name == "Acme-Corp.txt"
    assert written["json"].name == "Acme-Corp.json"


def test_json_report_is_machine_readable(tmp_path):
    path = report.write_all(_sample_report(), tmp_path, ("json",))["json"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["summary"]["query"] == "Acme Corp"
    assert payload["summary"]["results"] == 2
    assert payload["summary"]["mentions"] == {"acme": 3}
    assert payload["summary"]["proxies_used"] is False
    assert [row["url"] for row in payload["results"]] == [
        "https://one.example/", "https://two.example/"]
    assert payload["profiles"][0]["platform"] == "GitHub"
    assert payload["summary"]["detections"]["matched_signals"] == {
        "metadata": 1}
    assert payload["detections"]["handles"] == ["acme"]
    assert payload["detections"]["categories"] == {"dev": 1}
    assert payload["detections"]["verified"] == 1
    assert payload["detections"]["strengths"] == {"strong": 1}
    assert payload["results"][0]["handle"] == "acme"
    assert payload["results"][0]["category"] == "dev"
    assert payload["results"][0]["confidence"] == 90


def test_csv_report_has_a_row_per_result(tmp_path):
    path = report.write_all(_sample_report(), tmp_path, ("csv",))["csv"]
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["title"] for row in rows] == ["One", "Two"]
    assert rows[0]["engine"] == "duckduckgo"
    assert rows[0]["category"] == "dev"
    assert rows[0]["confidence"] == "90"
    assert rows[0]["handle"] == "acme"


def test_txt_and_markdown_include_the_summary(tmp_path):
    written = report.write_all(_sample_report(), tmp_path, ("txt", "md"))
    text = written["txt"].read_text(encoding="utf-8")
    assert "Total results: 2" in text
    assert "Unique mentions: 1" in text
    assert "Social profiles: 1" in text
    assert "timed out" in text
    assert "Detections" in text
    assert "Page metadata x1" in text
    assert "Handle: acme" in text
    assert "Verified: yes" in text
    markdown = written["md"].read_text(encoding="utf-8")
    assert markdown.startswith("# Ominis search: `Acme Corp`")
    assert "- Results: **2**" in markdown
    assert "## Detections" in markdown
    assert "Page metadata: **1**" in markdown
    # Detected profiles are listed with their platform and category.
    assert "## Detected platforms" in markdown
    assert "**GitHub**" in markdown
    assert "github.com/acme" in markdown
    assert "`acme`" in markdown


def test_detections_count_results_that_resolve_to_a_profile():
    outcome = report.SearchReport(
        query="acme",
        records=[
            report.SearchRecord(title="One", url="https://github.com/acme"),
            report.SearchRecord(title="Two", url="https://other.example/"),
        ],
        profiles=[{"platform": "GitHub",
                   "profile_url": "https://github.com/acme",
                   "source": "registry", "category": "dev"}])
    detections = outcome.detections()
    assert detections["resolved"] == 1
    assert detections["strengths"] == {"medium": 1}


def test_unknown_format_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown output format"):
        report.write_all(_sample_report(), tmp_path, ("xml",))
