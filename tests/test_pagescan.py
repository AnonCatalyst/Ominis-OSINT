"""Page evidence collection for search results."""

import httpx
import pytest

from ominis_src import pagescan, report

HTML = """
<html><head>
<title>Acme (acme) - GitHub</title>
<meta property="og:title" content="Acme (acme) - GitHub">
<meta name="description" content="Acme builds things.">
<link rel="canonical" href="https://github.com/acme">
</head><body><h1>Acme</h1></body></html>
"""

PROFILE_HTML = """
<html><head><title>Sign in</title></head>
<body>Please sign in to continue.</body></html>
"""


def test_inspect_page_uses_metadata_evidence():
    evidence = pagescan.inspect_page(
        "https://github.com/acme", 200, "https://github.com/acme",
        HTML, "acme")
    assert evidence["scanned"] is True
    assert evidence["matched"] is True
    assert evidence["signal"] == "metadata"
    assert evidence["platform"] == "GitHub"
    assert evidence["category"] == "dev"
    assert evidence["confidence"] == 90
    assert evidence["handle"] == "acme"
    assert "mentions the query" in evidence["detail"]


def test_inspect_page_keeps_an_unconfirmed_profile_as_a_url_lead():
    evidence = pagescan.inspect_page(
        "https://github.com/acme", 200, "https://github.com/acme",
        PROFILE_HTML, "unrelated")
    assert evidence["scanned"] is True
    assert evidence["matched"] is False
    assert evidence["signal"] == "url"
    assert evidence["platform"] == "GitHub"


def test_inspect_page_reports_http_errors_without_matching():
    evidence = pagescan.inspect_page(
        "https://github.com/acme", 403, "https://github.com/acme",
        "", "acme")
    assert evidence["scanned"] is True
    assert evidence["matched"] is False
    assert evidence["signal"] == "error"
    assert "403" in evidence["error"]


def test_inspect_page_without_a_query_stops_at_checked():
    evidence = pagescan.inspect_page(
        "https://example.com/", 200, "https://example.com/", HTML, "")
    assert evidence["matched"] is False
    assert evidence["signal"] == "checked"


class _Response:
    status_code = 200
    url = "https://github.com/acme"
    text = HTML


class _Client:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        _Client.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, timeout=None):
        return _Response()


@pytest.mark.asyncio
async def test_scan_records_fills_the_result_fields(monkeypatch):
    _Client.kwargs = {}
    monkeypatch.setattr(pagescan.httpx, "AsyncClient", _Client)
    record = report.SearchRecord(
        title="Acme", url="https://github.com/acme", engine="duckduckgo")
    tally = await pagescan.scan_records([record], "acme", limit=5)

    assert tally == {"scanned": 1, "matched": 1, "errors": 0}
    assert record.scanned is True
    assert record.matched is True
    assert record.signal == "metadata"
    assert record.status == 200
    assert record.final_url == "https://github.com/acme"
    assert record.platform == "GitHub"
    assert record.category == "dev"
    assert record.confidence == 90
    assert record.handle == "acme"
    assert _Client.kwargs["trust_env"] is False


@pytest.mark.asyncio
async def test_scan_records_honours_the_limit():
    record = report.SearchRecord(title="A", url="https://example.com/")
    other = report.SearchRecord(title="B", url="https://example.org/")
    tally = await pagescan.scan_records([record, other], "acme", limit=0)
    assert tally == {"scanned": 0, "matched": 0, "errors": 0}
    assert other.scanned is False


@pytest.mark.asyncio
async def test_scan_records_turns_transport_errors_into_rows(monkeypatch):
    class Broken(_Client):
        async def get(self, url, timeout=None):
            raise httpx.ConnectError("no route")

    monkeypatch.setattr(pagescan.httpx, "AsyncClient", Broken)
    record = report.SearchRecord(
        title="A", url="https://example.com/", engine="bing")
    tally = await pagescan.scan_records([record], "acme", limit=1)

    assert tally == {"scanned": 1, "matched": 0, "errors": 1}
    assert record.scanned is True
    assert record.matched is False
    assert record.signal == "error"
    assert "ConnectError" in record.error
