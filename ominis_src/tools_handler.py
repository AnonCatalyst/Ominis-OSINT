"""Search transport for the legacy 0.5.x build.

The interactive flow is unchanged. Proxies are passed only when the user opts
in, and the Google-style SerpBase API is an optional third engine.
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
from colorama import Fore, Style

from ominis_src.utils import (extract_mentions, find_social_profiles,
                              is_potential_forum)

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
)
MAX_RETRIES = 3
SERPBASE_ENDPOINT = "https://api.serpbase.dev/google/search"
COUNTER_EMOJIS = ["*", "+", ">", "#", "~", "=", ":", "|"]


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
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with httpx.AsyncClient(
                proxy=_pick_proxy(proxies), timeout=timeout,
                verify=verify_tls, follow_redirects=True,
                headers=_headers()) as client:
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
    try:
        async with httpx.AsyncClient(proxy=_pick_proxy(proxies), timeout=timeout,
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


async def fetch_engine_results(engine: str, query: str, start: int = 0,
                               proxies: tuple[str, ...] | None = None,
                               *, language: str = "", country: str = "",
                               date_range: tuple[str, str] = ("", ""),
                               serpbase_key: str = "", timeout: float = 15.0,
                               verify_tls: bool = True) -> list[dict[str, Any]]:
    if engine == "duckduckgo":
        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&s={start}"
        parser = parse_duckduckgo
    elif engine == "bing":
        url = f"https://www.bing.com/search?q={quote_plus(query)}&first={max(1, start)}"
        parser = parse_bing
    elif engine == "serpbase":
        return await fetch_serpbase(
            query, serpbase_key, language=language, country=country,
            date_range=date_range, page=max(1, start // 10 + 1),
            proxies=tuple(proxies or ()), timeout=timeout,
            verify_tls=verify_tls)
    else:
        raise SearchError(f"unsupported search engine: {engine}")
    html = await make_request_async(url, proxies, timeout=timeout,
                                    verify_tls=verify_tls)
    return parser(html)


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return (cleaned or "query")[:60]


def _write(records: list[dict[str, Any]], query: str,
           profiles: set[str], errors: list[str], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = _slug(query)
    txt = out_dir / f"{stem}_dual-engine_results.txt"
    data = out_dir / f"{stem}_dual-engine_results.json"
    with txt.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"Search Query: {query}\n{'=' * 80}\n")
        handle.write(f"Total results: {len(records)}\n")
        for item in records:
            handle.write("\n" + "-" * 80 + "\n")
            handle.write(f"[{item['engine']}] {item['title']}\n{item['url']}\n")
        if profiles:
            handle.write("\nSocial profiles:\n")
            handle.write("\n".join(sorted(profiles)) + "\n")
        if errors:
            handle.write("\nErrors:\n")
            handle.write("\n".join(f"- {error}" for error in errors) + "\n")
    data.write_text(json.dumps(
        {"query": query, "results": records, "profiles": sorted(profiles),
         "errors": errors, "total": len(records)},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"txt": str(txt), "json": str(data)}


async def fetch_dual_engine_results(query, language=None, country=None,
                                    date_range=None, proxies=None,
                                    max_results=100, **kwargs):
    """Keep the original entry point, with an optional SerpBase engine."""
    query = (query or "").strip()
    if not query:
        raise ValueError("query cannot be empty")
    date_range = date_range or ("", "")
    if isinstance(proxies, str):
        proxies = (proxies,)
    proxies = tuple(proxies or ())
    key = kwargs.get("serpbase_key") or os.environ.get("SERPBASE_API_KEY", "")
    timeout = float(kwargs.get("timeout", 15.0))
    verify_tls = bool(kwargs.get("verify_tls", True))
    out_dir = Path(kwargs.get("out_dir", "Results"))
    engines = ["duckduckgo", "bing"]
    if key:
        engines.append("serpbase")

    seen: set[str] = set()
    records: list[dict[str, Any]] = []
    mentions: list[dict[str, Any]] = []
    profiles: set[str] = set()
    errors: list[str] = []
    per_engine = max(1, int(max_results) // len(engines))

    print(f"{Fore.YELLOW}Starting search:{Fore.CYAN} "
          f"{', '.join(engines)}{Style.RESET_ALL}")
    print(f"{Fore.LIGHTBLACK_EX}Maximum results set to:{Fore.WHITE} "
          f"{max_results}{Style.RESET_ALL}")

    for engine in engines:
        start = 0
        engine_count = 0
        print(f"\n{Fore.YELLOW}Searching{Fore.LIGHTBLACK_EX}:{Fore.CYAN} "
              f"{engine.upper()}{Style.RESET_ALL}")
        while engine_count < per_engine and len(records) < max_results:
            try:
                rows = await fetch_engine_results(
                    engine, query, start, proxies, language=language or "",
                    country=country or "", date_range=date_range,
                    serpbase_key=key, timeout=timeout, verify_tls=verify_tls)
            except SearchError as exc:
                errors.append(f"{engine}: {exc}")
                print(f"{Fore.RED}{engine.upper()}: {exc}{Style.RESET_ALL}")
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
                engine_count += 1
                print("_" * 80)
                print(f"{random.choice(COUNTER_EMOJIS)} {Fore.YELLOW}Engine"
                      f"{Fore.LIGHTBLACK_EX}:{Fore.CYAN} {engine.upper()}"
                      f"{Style.RESET_ALL}")
                print(f"{random.choice(COUNTER_EMOJIS)} {Fore.YELLOW}Title"
                      f"{Fore.LIGHTBLACK_EX}: {Fore.BLUE}{row['title']}"
                      f"{Style.RESET_ALL}")
                print(f"{random.choice(COUNTER_EMOJIS)} {Fore.YELLOW}URL"
                      f"{Fore.LIGHTBLACK_EX}: {row['url']}{Style.RESET_ALL}")
                text = f"{row['title']} {row['url']}"
                for term, count in extract_mentions(text, query).items():
                    if count:
                        mentions.append({"url": row["url"], "term": term,
                                         "count": count})
                for profile in find_social_profiles(row["url"]):
                    profiles.add(profile["profile_url"])
                if engine_count >= per_engine or len(records) >= max_results:
                    break
                await asyncio.sleep(random.uniform(0.2, 0.6))
            if not added:
                break
            start += 10
            await asyncio.sleep(random.uniform(0.8, 1.6))

    paths = _write(records, query, profiles, errors, out_dir)
    print(f"\n{Fore.GREEN}Search completed!{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}Total results:{Fore.WHITE} {len(records)}")
    print(f"{Fore.YELLOW}Unique mentions found:{Fore.WHITE} {len(mentions)}")
    print(f"{Fore.YELLOW}Social profiles discovered:{Fore.WHITE} {len(profiles)}")
    for name, path in paths.items():
        print(f"{Fore.LIGHTBLACK_EX}{name}:{Fore.WHITE} {path}")
    if errors:
        print(f"{Fore.RED}{len(errors)} provider error(s); see the report."
              f"{Style.RESET_ALL}")
    return len(records), mentions, sorted(profiles)


async def dual_engine_search(query, proxies=None, max_results=100):
    return await fetch_dual_engine_results(query, proxies=proxies,
                                           max_results=max_results)


__all__ = [
    "SearchError", "fetch_dual_engine_results", "fetch_engine_results",
    "fetch_serpbase", "parse_bing", "parse_duckduckgo", "parse_serpbase",
    "make_request_async", "extract_mentions", "find_social_profiles",
    "is_potential_forum",
]
