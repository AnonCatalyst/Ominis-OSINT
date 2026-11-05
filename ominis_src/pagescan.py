"""Fetch search-result pages and record what the page itself proves.

Search snippets are claims made by a search engine. A result marked as a
profile should be checked against the page, the same way the username checker
does, so a stale snippet or a soft 404 cannot become a lead. This module is
deliberately separate from ``username`` because it works on arbitrary URLs,
not a platform template.
"""

from __future__ import annotations

import asyncio
import random
import urllib.parse
from typing import Iterable

import httpx

from . import platforms, report, username, utils

DEFAULT_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/126.0 Safari/537.36")
MAX_BODY_SCAN = username.MAX_BODY_SCAN


def _normalised(url: str) -> str:
    return str(url or "").strip().rstrip("/").casefold()


def _platform_for(url: str) -> dict[str, object]:
    detected = platforms.detect_profiles(url)
    return dict(detected[0]) if detected else {}


def _detail(signal: str, query: str, info: username.PageInfo,
            platform: str, final_url: str, error: str = "") -> str:
    if signal == "error":
        return error or "The page could not be read."
    if signal == "redirect":
        return f"The result resolved to {final_url}."
    if signal == "canonical":
        return "The page's canonical URL points at this result."
    if signal == "structured":
        return "Structured data on the page names this result."
    if signal == "metadata":
        return "The page title or metadata mentions the query."
    if signal == "body":
        return "Visible page content mentions the query."
    if signal == "url":
        if platform:
            return (f"The URL matches the {platform} profile shape, but the "
                    "page did not expose a matching mention.")
        return "The URL shape looks like a profile, but the page was not confirmed."
    return "The page loaded but did not mention the query."


def inspect_page(url: str, status: int, final_url: str, body: str,
                 query: str, error: str = "") -> dict[str, object]:
    """Return the evidence fields for one fetched page."""
    target = str(query or "").strip()
    platform_info = _platform_for(final_url or url)
    platform = str(platform_info.get("platform") or "")
    category = str(platform_info.get("category") or "")
    confidence = int(platform_info.get("confidence") or 0)
    result: dict[str, object] = {
        "status": int(status or 0),
        "final_url": final_url or url,
        "signal": "error" if error else "checked",
        "detail": "",
        "matched": False,
        "scanned": True,
        "platform": platform,
        "category": category,
        "confidence": confidence,
        "page_title": "",
        "page_description": "",
        "error": error,
    }
    if error:
        result["detail"] = _detail("error", target, username.PageInfo(),
                                   platform, final_url, error)
        return result
    if status and not 200 <= int(status) < 300:
        result["signal"] = "error"
        result["error"] = f"HTTP {status}"
        result["detail"] = f"The page returned HTTP {status}."
        return result

    info = username.parse_page_info(body or "")
    result["page_title"] = info.title or info.og_title
    result["page_description"] = info.description or info.og_description

    if not target:
        result["detail"] = "No query was supplied for page matching."
        return result

    requested = urllib.parse.urlsplit(url)
    final = urllib.parse.urlsplit(final_url or url)
    moved = _normalised(final_url or url) != _normalised(url)
    canonical = urllib.parse.urljoin(final_url or url, info.canonical) \
        if info.canonical else ""

    if moved and username._mentions(
            urllib.parse.unquote(final_url or ""), target):
        result["signal"] = "redirect"
        result["matched"] = True
        result["detail"] = _detail("redirect", target, info, platform,
                                   final_url or url)
        return result

    if (canonical and _normalised(canonical) != _normalised(url)
            and username._mentions(urllib.parse.unquote(canonical), target)):
        result["signal"] = "canonical"
        result["matched"] = True
        result["detail"] = _detail("canonical", target, info, platform,
                                   final_url or url)
        return result

    handles = " ".join(info.handles)
    if handles and username._mentions(handles, target):
        result["signal"] = "structured"
        result["matched"] = True
        result["detail"] = _detail("structured", target, info, platform,
                                   final_url or url)
        return result

    metadata = " ".join(part for part in (
        info.title, info.description, info.og_title, info.og_description) if part)
    if username._mentions(metadata, target):
        result["signal"] = "metadata"
        result["matched"] = True
        result["detail"] = _detail("metadata", target, info, platform,
                                   final_url or url)
        return result

    if info.visible and username._mentions(info.visible, target):
        result["signal"] = "body"
        result["matched"] = True
        result["detail"] = _detail("body", target, info, platform,
                                   final_url or url)
        return result

    if platform:
        result["signal"] = "url"
    result["detail"] = _detail(str(result["signal"]), target, info, platform,
                               final_url or url)
    return result


async def scan_records(records: Iterable[report.SearchRecord], query: str, *,
                       limit: int = 10, concurrency: int = 6,
                       timeout: float = 15.0,
                       proxies: tuple[str, ...] = (),
                       verify_tls: bool = True,
                       use_env_proxy: bool = False) -> dict[str, int]:
    """Scan up to ``limit`` records in place and return a small tally."""
    targets = [record for record in list(records)[:max(0, int(limit))]
               if str(record.url or "").startswith(("http://", "https://"))]
    if not targets:
        return {"scanned": 0, "matched": 0, "errors": 0}

    proxy = None
    if proxies:
        from .tools_handler import _normalize_proxy_pool

        proxy = random.choice(_normalize_proxy_pool(proxies))

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    semaphore = asyncio.Semaphore(max(1, int(concurrency)))
    limits = httpx.Limits(max_connections=max(2, concurrency),
                          max_keepalive_connections=max(2, concurrency))
    tally = {"scanned": 0, "matched": 0, "errors": 0}

    async with httpx.AsyncClient(
        proxy=proxy, verify=utils.ssl_verify(verify_tls),
        trust_env=use_env_proxy and proxy is None,
        headers=headers, limits=limits, timeout=timeout,
        follow_redirects=True,
    ) as client:
        async def one(record: report.SearchRecord) -> None:
            async with semaphore:
                try:
                    response = await client.get(record.url, timeout=timeout)
                except httpx.HTTPError as exc:
                    evidence = inspect_page(
                        record.url, 0, record.url, "", query,
                        error=username._error_text(exc))
                else:
                    evidence = inspect_page(
                        record.url, response.status_code, str(response.url),
                        response.text[:MAX_BODY_SCAN], query)
                record.status = int(evidence["status"] or 0)
                record.final_url = str(evidence["final_url"] or record.url)
                record.signal = str(evidence["signal"] or "")
                record.detail = str(evidence["detail"] or "")
                record.matched = bool(evidence["matched"])
                record.scanned = True
                record.platform = str(evidence["platform"] or "")
                record.page_title = str(evidence["page_title"] or "")
                record.page_description = str(evidence["page_description"] or "")
                record.error = str(evidence["error"] or "")
                tally["scanned"] += 1
                if record.matched:
                    tally["matched"] += 1
                if record.error:
                    tally["errors"] += 1

        await asyncio.gather(*(one(record) for record in targets))
    return tally
