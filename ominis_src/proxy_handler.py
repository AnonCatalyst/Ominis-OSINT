"""Opt-in proxy harvesting for the legacy build."""

from __future__ import annotations

import asyncio
import random
import re

import httpx
from bs4 import BeautifulSoup

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
)
PROXY_SOURCES = (
    "https://www.sslproxies.org/",
    "https://free-proxy-list.net/",
)
VALIDATION_URL = "https://example.com/"
MAX_CANDIDATES = 200


def _clean(value: str) -> str:
    value = value.strip()
    return value if "://" in value else f"http://{value}"


def _looks_like_proxy(value: str) -> bool:
    return bool(re.fullmatch(r"(?:\w+://)?[^:\s/]+:\d{1,5}", value.strip()))


async def fetch_proxies_from_site(proxy_url: str) -> list[str]:
    proxies: list[str] = []
    headers = {"User-Agent": random.choice(USER_AGENTS)}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True,
                                     headers=headers) as client:
            response = await client.get(proxy_url)
            response.raise_for_status()
    except httpx.HTTPError:
        return proxies

    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.find("table")
    if not table:
        return proxies
    for row in table.find_all("tr"):
        cells = row.find_all("td", limit=2)
        if len(cells) != 2:
            continue
        candidate = f"{cells[0].get_text(strip=True)}:{cells[1].get_text(strip=True)}"
        if _looks_like_proxy(candidate):
            proxies.append(candidate)
        if len(proxies) >= MAX_CANDIDATES:
            break
    return proxies


async def scrape_proxies() -> list[str]:
    results = await asyncio.gather(
        *(fetch_proxies_from_site(url) for url in PROXY_SOURCES),
        return_exceptions=True)
    seen: set[str] = set()
    proxies: list[str] = []
    for group in results:
        if isinstance(group, Exception):
            continue
        for item in group:
            if item not in seen:
                seen.add(item)
                proxies.append(item)
    return proxies


async def validate_proxies(proxies: list[str], *, timeout: float = 10.0,
                           limit: int = 100) -> list[str]:
    valid: list[str] = []
    queue = list(dict.fromkeys(_clean(item) for item in proxies))[:limit]
    headers = {"User-Agent": random.choice(USER_AGENTS)}

    async def check(proxy: str) -> str | None:
        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=timeout,
                                         verify=True,
                                         follow_redirects=True,
                                         headers=headers) as client:
                response = await client.get(VALIDATION_URL)
                return proxy if response.status_code == 200 else None
        except httpx.HTTPError:
            return None

    for start in range(0, len(queue), 20):
        batch = queue[start:start + 20]
        checked = await asyncio.gather(*(check(proxy) for proxy in batch))
        valid.extend(proxy for proxy in checked if proxy)
        print(f"Validated: {min(start + 20, len(queue))}/{len(queue)} proxies",
              end="\r")
    if queue:
        print()
    return valid


async def main() -> None:
    candidates = await scrape_proxies()
    valid = await validate_proxies(candidates)
    print(f"\nTotal valid proxies found: {len(valid)}")


if __name__ == "__main__":
    asyncio.run(main())
