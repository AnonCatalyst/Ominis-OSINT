"""Search transport for the ARG build.

No browser impersonation, no validation side effects and no log files. Proxies
are used only when the caller passes them. The Google leg can be served by
SerpBase when a key is present.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import random
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
from bs4 import BeautifulSoup

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
)
MAX_RETRIES = 3
SERPBASE_ENDPOINT = "https://api.serpbase.dev/google/search"


class SearchError(RuntimeError):
    """A provider could not be queried."""


def _normalise_proxy(value: str) -> str:
    value = value.strip()
    return value if "://" in value else f"http://{value}"


def _pick_proxy(proxies: tuple[str, ...] | list[str] | None) -> str | None:
    if not proxies:
        return None
    return _normalise_proxy(random.choice(list(proxies)))


def _headers() -> dict[str, str]:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.8",
    }


async def make_request_async(url: str, proxies: tuple[str, ...] | None = None,
                             *, timeout: float = 15.0,
                             verify_tls: bool = True) -> str:
    """Fetch one page with bounded retries and an explicit proxy choice."""
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        proxy = _pick_proxy(proxies)
        try:
            async with httpx.AsyncClient(
                proxy=proxy,
                timeout=timeout,
                verify=verify_tls,
                follow_redirects=True,
                headers=_headers(),
            ) as client:
                response = await client.get(url)
                if response.status_code in (403, 429):
                    raise SearchError(f"blocked with HTTP {response.status_code}")
                response.raise_for_status()
                return response.text
        except (httpx.HTTPError, SearchError) as exc:
            last_error = exc
            if attempt < MAX_RETRIES:
                await asyncio.sleep(min(2 ** attempt, 8))
    raise SearchError(f"request failed after {MAX_RETRIES} attempts: {last_error}")


def _unwrap_ddg(href: str) -> str:
    if not href:
        return ""
    if href.startswith("//"):
        href = "https:" + href
    if "duckduckgo.com/l/" in href or href.startswith("/l/"):
        parsed = urlparse(href)
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    return href


def _unwrap_bing(href: str) -> str:
    if not href:
        return ""
    if "bing.com/ck/a" in href:
        parsed = urlparse(href)
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            encoded = encoded[2:]
        try:
            padded = encoded + "=" * (-len(encoded) % 4)
            return base64.urlsafe_b64decode(padded).decode("utf-8", "replace")
        except (ValueError, UnicodeDecodeError):
            return ""
    return href


def _valid(url: str) -> bool:
    return isinstance(url, str) and url.startswith("http")


def _result(engine: str, title: str, url: str, snippet: str,
            position: int) -> dict[str, Any]:
    return {"engine": engine, "title": title or url, "url": url,
            "snippet": snippet, "position": position}


def parse_google(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for block in soup.select("div.tF2Cxc, div.MjjYud, div.g"):
        link = block.select_one("a[href]")
        if not link:
            continue
        href = link.get("href", "")
        if href.startswith("/url?"):
            href = parse_qs(urlparse(href).query).get("q", [""])[0]
        if not _valid(href):
            continue
        heading = block.select_one("h3")
        snippet_node = block.select_one(".VwiC3b, .IsZvec, .aCOpRe")
        rows.append(_result("google", heading.get_text(" ", strip=True)
                            if heading else href, href,
                            snippet_node.get_text(" ", strip=True)
                            if snippet_node else "", len(rows) + 1))
    return rows


def parse_duckduckgo(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for block in soup.select("div.result"):
        link = block.select_one("a.result__a")
        if not link:
            continue
        href = _unwrap_ddg(link.get("href", ""))
        if not _valid(href) or "duckduckgo.com/y.js" in href:
            continue
        snippet = block.select_one(".result__snippet")
        rows.append(_result("duckduckgo", link.get_text(" ", strip=True),
                            href, snippet.get_text(" ", strip=True)
                            if snippet else "", len(rows) + 1))
    return rows


def parse_bing(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, Any]] = []
    for block in soup.select("li.b_algo"):
        heading = block.find("h2")
        link = heading.find("a", href=True) if heading else None
        if not link:
            continue
        href = _unwrap_bing(link.get("href", ""))
        if not _valid(href):
            continue
        snippet = block.select_one(".b_caption p") or block.select_one("p")
        rows.append(_result("bing", heading.get_text(" ", strip=True),
                            href, snippet.get_text(" ", strip=True)
                            if snippet else "", len(rows) + 1))
    return rows


def _find_items(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("organic", "results", "organic_results", "items", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            nested = _find_items(value)
            if nested:
                return nested
    return []


def parse_serpbase(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(_find_items(payload), start=1):
        if not isinstance(item, dict):
            continue
        url = item.get("link") or item.get("url") or item.get("href") or ""
        if not _valid(url):
            continue
        rows.append(_result(
            "serpbase",
            str(item.get("title") or item.get("name") or url),
            url,
            str(item.get("snippet") or item.get("description") or ""),
            int(item.get("position") or index),
        ))
    return rows


async def fetch_serpbase(query: str, key: str, *, language: str = "",
                         country: str = "", date_range: tuple[str, str] = ("", ""),
                         page: int = 1, proxies: tuple[str, ...] = (),
                         timeout: float = 15.0,
                         verify_tls: bool = True) -> list[dict[str, Any]]:
    if not key:
        raise SearchError("no SerpBase API key configured")
    body: dict[str, Any] = {"q": query, "page": max(1, page)}
    if country:
        body["gl"] = country.lower()
    if language:
        body["hl"] = language.lower()
    start, end = date_range
    if start or end:
        start = start.replace("-", "/")
        end = end.replace("-", "/")
        body["q"] = f"{query} after:{start} before:{end}".replace("  ", " ").strip()
    proxy = _pick_proxy(proxies)
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=timeout,
                                     verify=verify_tls,
                                     follow_redirects=True) as client:
            response = await client.post(
                SERPBASE_ENDPOINT, json=body,
                headers={"Accept": "application/json",
                         "Content-Type": "application/json",
                         "X-API-Key": key})
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise SearchError(
            f"SerpBase returned HTTP {exc.response.status_code}") from None
    except (httpx.HTTPError, json.JSONDecodeError, ValueError) as exc:
        raise SearchError(f"SerpBase request failed: {exc}") from None
    if isinstance(payload, dict):
        status = payload.get("status")
        if status not in (None, 0, "0"):
            detail = payload.get("error") or payload.get("message") or status
            raise SearchError(f"SerpBase returned status {detail}")
    return parse_serpbase(payload)


def google_url(query: str, page: int = 0, language: str = "",
               country: str = "", date_range: tuple[str, str] = ("", "")) -> str:
    params = {"q": query, "start": max(0, page)}
    if language:
        params["lr"] = language
    if country:
        params["cr"] = country
    start, end = date_range
    if start or end:
        params["tbs"] = f"cdr:1,cd_min:{start},cd_max:{end}"
    return "https://www.google.com/search?" + "&".join(
        f"{key}={quote_plus(str(value))}" for key, value in params.items())


async def fetch_engine(engine: str, query: str, *, page: int = 0,
                       language: str = "", country: str = "",
                       date_range: tuple[str, str] = ("", ""),
                       proxies: tuple[str, ...] = (),
                       serpbase_key: str = "", timeout: float = 15.0,
                       verify_tls: bool = True) -> list[dict[str, Any]]:
    if engine == "serpbase":
        return await fetch_serpbase(
            query, serpbase_key, language=language, country=country,
            date_range=date_range, page=max(1, page // 10 + 1),
            proxies=proxies, timeout=timeout, verify_tls=verify_tls)
    if engine == "google":
        url = google_url(query, page, language, country, date_range)
        parser = parse_google
    elif engine == "duckduckgo":
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&s={page}"
        parser = parse_duckduckgo
    elif engine == "bing":
        url = f"https://www.bing.com/search?q={quote_plus(query)}&first={max(1, page)}"
        parser = parse_bing
    else:
        raise SearchError(f"unknown engine: {engine}")
    html = await make_request_async(url, proxies, timeout=timeout,
                                    verify_tls=verify_tls)
    return parser(html)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return (cleaned or "query")[:60]


def _write(records: list[dict[str, Any]], query: str, errors: list[str],
           out_dir: Path, engines: tuple[str, ...]) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _slug(query)
    txt = out_dir / f"{stem}.txt"
    data = out_dir / f"{stem}.json"
    with txt.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"Query: {query}\nEngines: {', '.join(engines)}\n")
        handle.write(f"Results: {len(records)}\n")
        for item in records:
            handle.write("\n" + "-" * 80 + "\n")
            handle.write(f"[{item['engine']}] {item['title']}\n{item['url']}\n")
            if item["snippet"]:
                handle.write(f"{item['snippet']}\n")
        if errors:
            handle.write("\nErrors:\n")
            handle.write("\n".join(f"- {error}" for error in errors) + "\n")
    data.write_text(json.dumps(
        {"query": query, "engines": list(engines), "results": records,
         "errors": errors, "total": len(records)},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"txt": str(txt), "json": str(data)}


async def fetch_results(query: str, *, engines: tuple[str, ...] = ("google",),
                        language: str = "", country: str = "",
                        date_range: tuple[str, str] = ("", ""),
                        proxies: tuple[str, ...] = (), max_results: int = 100,
                        out_dir: Path = Path("Results"), serpbase_key: str = "",
                        timeout: float = 15.0,
                        verify_tls: bool = True) -> dict[str, Any]:
    if not query.strip():
        raise ValueError("query cannot be empty")
    language = _normalise_language(language)
    country = _normalise_country(country)
    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    errors: list[str] = []

    for engine in engines:
        page = 0
        while len(records) < max_results:
            try:
                rows = await fetch_engine(
                    engine, query, page=page, language=language,
                    country=country, date_range=date_range, proxies=proxies,
                    serpbase_key=serpbase_key, timeout=timeout,
                    verify_tls=verify_tls)
            except SearchError as exc:
                errors.append(f"{engine}: {exc}")
                break
            if not rows:
                break
            added = 0
            for row in rows:
                if row["url"] in seen:
                    continue
                seen.add(row["url"])
                records.append(row)
                added += 1
                if len(records) >= max_results:
                    break
                await asyncio.sleep(random.uniform(0.2, 0.6))
            if not added:
                break
            page += 10
            await asyncio.sleep(random.uniform(0.8, 1.6))

    paths = _write(records, query, errors, Path(out_dir), engines)
    return {"records": records, "errors": errors, "paths": paths}


def _normalise_language(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return value if value.startswith("lang_") else f"lang_{value}"


def _normalise_country(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    return value if value.startswith("country") else f"country{value.upper()}"


def extract_mentions(text: str, query: str) -> dict[str, int]:
    return {word: len(re.findall(re.escape(word), text, re.IGNORECASE))
            for word in query.split() if word}
