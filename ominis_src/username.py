"""Username search across a list of platform URL templates.

The old implementation opened one ``requests_html`` browser per URL, which
needs a Chromium download on first use and leaked sessions on error. This one
uses one shared HTTPX client, a bounded number of concurrent checks, and a
per-request timeout.
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import httpx

from . import config, report

DEFAULT_PLATFORMS = Path(__file__).with_name("urls.txt")
DEFAULT_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/126.0 Safari/537.36")
_SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")
MAX_BODY_SCAN = 200_000


@dataclass
class Hit:
    username: str
    url: str
    status: int = 0
    title: str = ""
    description: str = ""
    matched: bool = False
    error: str = ""

    @property
    def found(self) -> bool:
        return self.matched and not self.error


@dataclass
class UsernameReport:
    username: str
    started: str = field(default_factory=lambda: datetime.now(timezone.utc)
                         .isoformat(timespec="seconds"))
    hits: list[Hit] = field(default_factory=list)

    @property
    def found(self) -> list[Hit]:
        return [hit for hit in self.hits if hit.found]

    @property
    def errors(self) -> list[Hit]:
        return [hit for hit in self.hits if hit.error]


def profile_url(base: str, username: str) -> str:
    base = base.strip()
    if not base:
        raise ValueError("empty platform URL")
    if username.lower() in base.lower():
        return base
    return base + username if base.endswith(("/", "@")) else f"{base}/{username}"


def load_platforms(path: str | Path = DEFAULT_PLATFORMS) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    return [line.strip() for line in lines
            if line.strip() and not line.lstrip().startswith("#")]


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_page(body: str, username: str) -> tuple[str, str]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body[:MAX_BODY_SCAN], "html.parser")
    title = _text(soup.title)
    node = soup.find("meta", attrs={"name": "description"})
    description = str(node.get("content", "")) if node else ""
    return title, description


async def check_one(client: httpx.AsyncClient, username: str, base: str,
                    *, timeout: float = 15.0, scan_body: bool = True) -> Hit:
    url = profile_url(base, username)
    needle = username.casefold()
    try:
        response = await client.get(url, timeout=timeout,
                                    follow_redirects=True)
    except httpx.HTTPError as exc:
        return Hit(username=username, url=url,
                   error=f"{type(exc).__name__}: {exc}")
    hit = Hit(username=username, url=str(response.url),
              status=response.status_code)
    if response.status_code != 200:
        return hit
    title, description = parse_page(response.text, username)
    hit.title, hit.description = title, description
    # The requested URL always contains the username, so only a redirect to a
    # different address says anything about the profile.
    redirected = str(response.url) != url and needle in str(response.url).casefold()
    hit.matched = (redirected
                   or needle in title.casefold()
                   or needle in description.casefold())
    if not hit.matched and scan_body:
        hit.matched = needle in response.text[:MAX_BODY_SCAN].casefold()
    return hit


async def run(username: str, platforms: Iterable[str] | None = None, *,
              concurrency: int = 8, timeout: float = 15.0,
              proxies: tuple[str, ...] = (), verify_tls: bool = True,
              progress: Callable[[Hit], None] | None = None) -> UsernameReport:
    username = str(username or "").strip()
    if not username:
        raise ValueError("a username search needs a username")
    if not _SAFE_NAME.fullmatch(username):
        raise ValueError("usernames may only contain letters, digits, '.', '_' and '-'")
    templates = list(platforms) if platforms is not None else load_platforms()
    if not templates:
        raise ValueError("no platform URLs to check")

    outcome = UsernameReport(username=username)
    proxy = None
    if proxies:
        from .tools_handler import _normalize_proxy_pool

        proxy = _normalize_proxy_pool(proxies)[0]

    limits = httpx.Limits(max_connections=max(2, concurrency),
                          max_keepalive_connections=max(2, concurrency))
    headers = {"User-Agent": DEFAULT_USER_AGENT,
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async with httpx.AsyncClient(proxy=proxy, verify=verify_tls,
                                 headers=headers, limits=limits,
                                 timeout=timeout) as client:
        async def worker(base: str) -> Hit:
            async with semaphore:
                hit = await check_one(client, username, base, timeout=timeout)
                if progress:
                    progress(hit)
                return hit

        outcome.hits = list(await asyncio.gather(*(worker(base) for base in templates)))
    return outcome


def run_sync(username: str, **kwargs: object) -> UsernameReport:
    return asyncio.run(run(username, **kwargs))  # type: ignore[arg-type]


def write(outcome: UsernameReport, out_dir: str | Path = "Results",
          formats: tuple[str, ...] | list[str] = ("txt", "json")) -> dict[str, str]:
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = report.results_path(directory, f"username-{outcome.username}", "")
    written: dict[str, str] = {}
    for name in formats:
        if name == "json":
            path = stem.with_suffix(".json") if stem.suffix != ".json" else stem
            path.write_text(json.dumps({
                "username": outcome.username,
                "started": outcome.started,
                "found": len(outcome.found),
                "checked": len(outcome.hits),
                "profiles": [asdict(hit) for hit in outcome.found],
                "errors": [asdict(hit) for hit in outcome.errors],
            }, indent=2, ensure_ascii=False), encoding="utf-8")
        elif name == "csv":
            path = stem.with_suffix(".csv")
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["username", "url", "status", "title",
                                        "description", "matched", "error"])
                writer.writeheader()
                for hit in outcome.hits:
                    writer.writerow(asdict(hit))
        elif name == "md":
            path = stem.with_suffix(".md")
            lines = [f"# Username search: `{outcome.username}`", "",
                     f"_{outcome.started}_", "",
                     f"Checked **{len(outcome.hits)}** platforms, "
                     f"found **{len(outcome.found)}** profiles.", ""]
            for hit in outcome.found:
                lines.append(f"- [{hit.title or hit.url}]({hit.url}) - {hit.status}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            path = stem.with_suffix(".txt")
            lines = [f"Username: {outcome.username}",
                     f"Started: {outcome.started}", "=" * 78]
            for hit in outcome.found:
                lines += [f"URL: {hit.url}", f"Status: {hit.status}"]
                if hit.title:
                    lines.append(f"Title: {hit.title}")
                if hit.description:
                    lines.append(f"Description: {hit.description}")
                lines.append("-" * 78)
            lines += ["", f"Found {len(outcome.found)} of {len(outcome.hits)} platforms."]
            if outcome.errors:
                lines.append(f"Errors: {len(outcome.errors)}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written[name] = str(path)
    return written


def settings_proxies(settings: config.Settings) -> tuple[str, ...]:
    return settings.proxies
