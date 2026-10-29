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
                                engine="duckduckgo", snippet="first", position=1),
            report.SearchRecord(title="Two", url="https://two.example/",
                                engine="bing", snippet="second", position=2),
        ],
        mentions={"acme": 3},
        profiles=[{"platform": "GitHub", "profile_url": "github.com/acme"}],
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


def test_csv_report_has_a_row_per_result(tmp_path):
    path = report.write_all(_sample_report(), tmp_path, ("csv",))["csv"]
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["title"] for row in rows] == ["One", "Two"]
    assert rows[0]["engine"] == "duckduckgo"


def test_txt_and_markdown_include_the_summary(tmp_path):
    written = report.write_all(_sample_report(), tmp_path, ("txt", "md"))
    text = written["txt"].read_text(encoding="utf-8")
    assert "Total results: 2" in text
    assert "Unique mentions: 1" in text
    assert "Social profiles: 1" in text
    assert "timed out" in text
    markdown = written["md"].read_text(encoding="utf-8")
    assert markdown.startswith("# Ominis search: `Acme Corp`")
    assert "github.com/acme" not in markdown  # profiles are counted, not linked
    assert "- Results: **2**" in markdown


def test_unknown_format_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown output format"):
        report.write_all(_sample_report(), tmp_path, ("xml",))
