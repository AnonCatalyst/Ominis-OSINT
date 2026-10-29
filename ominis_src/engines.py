"""Search providers.

Each provider turns a query plus filters into the same small record, so the
rest of Ominis does not care whether a result came from a scraped page or a
paid results API.

DuckDuckGo and Bing are scraped with the transport in ``tools_handler`` (the
one place that knows about proxies and TLS). SerpBase is optional: when a key
is present, the Google leg goes through the API, otherwise the scraper stays
the only path.
"""

from __future__ import annotations

import json
import urllib.parse
from dataclasses import dataclass
from typing import Any

import httpx

from . import config, utils

ENGINE_LABELS = {
    "duckduckgo": "DuckDuckGo",
    "bing": "Bing",
    "serpbase": "SerpBase (Google)",
}


class EngineError(RuntimeError):
    """A provider could not answer; callers decide whether to continue."""


@dataclass
class Result:
    title: str
    url: str
    engine: str
    snippet: str = ""
    position: int = 0


def _region(language: str, country: str) -> str:
    if language and country:
        return f"{country.lower()}-{language.lower()}"
    return (country or language or "").lower()


def _date_filter(since: str, until: str) -> str:
    if since and until:
        return f"{since}..{until}"
    if since:
        return f"{since}.."
    return ""


def duckduckgo_url(query: str, page: int = 0, language: str = "",
                   country: str = "", since: str = "", until: str = "") -> str:
    params = {"q": query, "s": str(page)}
    region = _region(language, country)
    if region:
        params["kl"] = region
    date_filter = _date_filter(since, until)
    if date_filter:
        params["df"] = date_filter
    return "https://html.duckduckgo.com/html/?" + urllib.parse.urlencode(params)


def bing_url(query: str, page: int = 0, language: str = "",
             country: str = "", since: str = "", until: str = "") -> str:
    params = {"q": query, "first": str(page)}
    if country:
        params["cc"] = country.upper()
    if language:
        params["setlang"] = language.lower()
    if since or until:
        start = since or "1970-01-01"
        end = until or "9999-12-31"
        params["filters"] = f'ex1:"ez5_{start}_{end}"'
    return "https://www.bing.com/search?" + urllib.parse.urlencode(params)


def parse_duckduckgo(html: str) -> list[Result]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[Result] = []
    for position, block in enumerate(soup.select(".result"), start=1):
        link = block.find("a", class_="result__a")
        if not link:
            continue
        href = utils.unwrap_duckduckgo_url(link.get("href", ""))
        if not href.startswith("http"):
            continue
        tracked = urllib.parse.urlparse(href)
        if ((tracked.hostname or "").endswith("duckduckgo.com")
                and tracked.path.startswith("/y.js")):
            continue  # sponsored placement
        snippet = ""
        node = block.select_one(".result__snippet")
        if node:
            snippet = node.get_text(" ", strip=True)
        results.append(Result(title=link.get_text(" ", strip=True) or href,
                              url=href, engine="duckduckgo",
                              snippet=snippet, position=position))
    return results


def parse_bing(html: str) -> list[Result]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[Result] = []
    for position, block in enumerate(soup.select(".b_algo"), start=1):
        heading = block.find("h2")
        link = block.find("a", href=True)
        if not heading or not link:
            continue
        href = utils.unwrap_bing_url(link["href"])
        if not href.startswith("http"):
            continue
        snippet = ""
        node = block.select_one(".b_caption p") or block.select_one("p")
        if node:
            snippet = node.get_text(" ", strip=True)
        results.append(Result(title=heading.get_text(" ", strip=True) or href,
                              url=href, engine="bing",
                              snippet=snippet, position=position))
    return results


def parse_serpbase(payload: Any) -> list[Result]:
    """Read either a flat list or the common nested JSON envelopes."""
    items = _find_items(payload)
    results: list[Result] = []
    for position, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("link") or item.get("href") or ""
        if not isinstance(url, str) or not url.startswith("http"):
            continue
        title = item.get("title") or item.get("name") or url
        snippet = item.get("snippet") or item.get("description") or item.get("text") or ""
        results.append(Result(title=str(title), url=url, engine="serpbase",
                              snippet=str(snippet),
                              position=int(item.get("position") or position)))
    return results


def _find_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("results", "organic_results", "organic", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _find_items(value)
            if nested:
                return nested
    return []


async def fetch_serpbase(query: str, key: str, *, language: str = "",
                         country: str = "", since: str = "", until: str = "",
                         page: int = 1, per_page: int = 20,
                         proxies: tuple[str, ...] = (),
                         timeout: float = 15.0,
                         verify_tls: bool = True,
                         endpoint: str = config.SERPBASE_ENDPOINT) -> list[Result]:
    """Query a SerpBase-compatible Google results API.

    The API takes a JSON body and returns one page of ``organic`` results. It
    does not accept a page size, so ``per_page`` is kept for callers that share
    the engine signature and is not sent.
    """
    if not key:
        raise EngineError("no SerpBase API key configured")
    body: dict[str, str | int] = {"q": query, "page": max(1, int(page))}
    if country:
        body["gl"] = country.lower()
    if language:
        body["hl"] = language.lower()
    if since or until:
        # Google's own date operator, passed through as part of the query.
        start = since.replace("-", "/") if since else ""
        end = until.replace("-", "/") if until else ""
        body["q"] = f"{query} after:{start} before:{end}".replace("  ", " ").strip()

    headers = {"Accept": "application/json", "Content-Type": "application/json",
               "X-API-Key": key}
    proxy = None
    if proxies:
        from .tools_handler import _normalize_proxy_pool

        proxy = _normalize_proxy_pool(proxies)[0]

    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=timeout,
                                     verify=verify_tls,
                                     follow_redirects=True) as client:
            response = await client.post(endpoint, json=body, headers=headers)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise EngineError(
            f"SerpBase returned HTTP {exc.response.status_code}") from None
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        raise EngineError(f"SerpBase request failed: {exc}") from None
    if isinstance(payload, dict):
        status = payload.get("status")
        if status not in (None, 0, "0"):
            detail = payload.get("error") or payload.get("message") or status
            raise EngineError(f"SerpBase returned status {detail}")
    return parse_serpbase(payload)


async def fetch_engine(engine: str, settings: config.Settings, page: int) -> list[Result]:
    """Fetch one page from one provider."""
    if engine == "serpbase":
        return await fetch_serpbase(
            settings.query, settings.serpbase_key,
            language=settings.language, country=settings.country,
            since=settings.since, until=settings.until,
            page=page, per_page=min(20, settings.page_size),
            proxies=settings.proxies, timeout=settings.timeout,
            verify_tls=settings.verify_tls)

    if engine not in ("duckduckgo", "bing"):
        raise EngineError(f"unknown engine: {engine}")

    from . import tools_handler

    if engine == "duckduckgo":
        offset = (page - 1) * 10
        url = duckduckgo_url(settings.query, offset, settings.language,
                             settings.country, settings.since, settings.until)
        parser = parse_duckduckgo
    else:
        offset = (page - 1) * 10 + 1
        url = bing_url(settings.query, offset, settings.language,
                       settings.country, settings.since, settings.until)
        parser = parse_bing

    text = await tools_handler.make_request_async(url, settings.proxies or None)
    if not text:
        return []
    return parser(text)


def mention_counts(text: str, query: str) -> dict[str, int]:
    return utils.extract_mentions(text, query)
