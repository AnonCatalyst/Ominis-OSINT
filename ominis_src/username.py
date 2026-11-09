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
import urllib.parse
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

import httpx

from . import config, platforms, report, utils

DEFAULT_PLATFORMS = Path(__file__).with_name("urls.txt")
DEFAULT_USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/126.0 Safari/537.36")
_SAFE_NAME = re.compile(r"[A-Za-z0-9._-]{1,64}")
#: YouTube and Pinterest put hundreds of kilobytes of script before the
#: <title> tag. A 200 KB cap silently missed every YouTube profile.
MAX_BODY_SCAN = 2_000_000
#: Titles that say the account is gone, even when they return HTTP 200.
_MISSING_MARKERS = (
    "404", "not found", "page not found", "doesn't exist", "does not exist",
    "user not found", "profile not found", "no longer available",
    # The platform list covers regional sites; a Russian-language "profile
    # does not exist" title was being reported as a live profile.
    "не существует", "не найден", "не найдена", "страница не найдена",
)
#: Visible body text that means the same thing. A bare "404" is not included
#: because it also appears in scripts and footers on real profile pages.
_BODY_MISSING_MARKERS = (
    "user not found", "profile not found", "page not found",
    "account not found", "doesn't exist", "does not exist",
    "no longer available", "не существует", "не найден", "не найдена",
)
_HANDLE_CHARS = "A-Za-z0-9_.-"


@dataclass
class Hit:
    username: str
    url: str
    status: int = 0
    title: str = ""
    description: str = ""
    matched: bool = False
    match: str = ""
    error: str = ""
    platform: str = ""
    category: str = ""
    confidence: int = 0
    #: The account identifier the check read from the URL or page.
    handle: str = ""
    source: str = "local"

    @property
    def found(self) -> bool:
        return self.matched and not self.error


@dataclass
class PageInfo:
    """What the page head says about the profile.

    Only metadata is read here; a body-wide search happens separately and only
    when the head does not already answer. This keeps a footer mention or a
    canonical link from turning a soft 404 into a "found".
    """

    title: str = ""
    description: str = ""
    og_title: str = ""
    og_description: str = ""
    canonical: str = ""
    og_url: str = ""
    handles: tuple[str, ...] = ()
    visible: str = ""
    embedded_missing: bool = False


_EMBEDDED_MISSING = re.compile(
    r'"(?:httpStatus|status)"\s*:\s*404|"httpErrorPage"', re.IGNORECASE)
_HANDLE_KEYS = (
    "uniqueId", "vanityChannelUrl", "canonicalBaseUrl", "alternateName",
    "username", "login", "screen_name",
)
_HANDLE_JSON = re.compile(
    r'"(?:' + "|".join(_HANDLE_KEYS) + r')"\s*:\s*"([^"]{1,200})"',
    re.IGNORECASE)


STATE_LABELS = report.SIGNAL_LABELS


def _tally(values: Iterable[object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "").strip()
        if key:
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


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

    def detections(self) -> dict[str, object]:
        """Roll up what confirmed the profiles this check found."""
        found = self.found
        return {
            "signals": _tally(hit.match for hit in self.hits if hit.match),
            "matched_signals": _tally(hit.match for hit in found),
            "sources": _tally(hit.source for hit in self.hits),
            "categories": _tally(hit.category for hit in found),
            "platforms": _tally(hit.platform for hit in found),
            "handles": sorted({hit.handle for hit in found if hit.handle}),
            "leads": len(found),
            "verified": sum(1 for hit in found if hit.matched),
            "strengths": _tally(
                report.SIGNAL_STRENGTH.get(
                    hit.match, "strong" if hit.matched else "none")
                for hit in found),
        }

    def summary(self) -> dict[str, object]:
        return {
            "username": self.username,
            "started": self.started,
            "found": len(self.found),
            "checked": len(self.hits),
            "errors": len(self.errors),
            "detections": self.detections(),
        }


def profile_url(base: str, username: str) -> str:
    base = base.strip()
    if not base:
        raise ValueError("empty platform URL")
    if "{username}" in base:
        return base.replace("{username}", username)
    parsed = urllib.parse.urlsplit(base)
    segments = [part for part in parsed.path.split("/") if part]
    if segments and segments[-1].lstrip("@~") == username:
        return base
    # Query templates such as ``?gamertag=`` and ``&u=`` take the handle
    # directly; adding a slash would produce ``?gamertag=/acme``.
    if base.endswith(("/", "@", "=", "?", "&", ":")):
        return base + username
    return f"{base}/{username}"


def load_platforms(path: str | Path = DEFAULT_PLATFORMS) -> list[str]:
    # utf-8-sig drops the BOM Notepad and PowerShell add to a saved list.
    # Without it the first URL keeps an invisible character and fails with
    # "Request URL is missing an 'http://' or 'https://' protocol".
    lines = Path(path).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    templates: list[str] = []
    seen: set[str] = set()
    for line in lines:
        template = line.strip()
        if not template or template.startswith("#"):
            continue
        if template in seen:
            continue
        seen.add(template)
        templates.append(template)
    return templates


def _text(node) -> str:
    return utils.clean_text(node.get_text(" ", strip=True)) if node else ""


def _meta(soup, attribute: str, value: str) -> str:
    node = soup.find("meta", attrs={attribute: value})
    return utils.clean_text(node.get("content", "")) if node else ""


def _handle_from_value(value: str) -> str:
    """Reduce ``/@name``, ``https://host/@name`` and ``@name`` to ``name``."""
    text = utils.clean_text(value).strip("\"'")
    if not text:
        return ""
    text = text.split("?", 1)[0].split("#", 1)[0]
    if "/" in text:
        text = [part for part in text.split("/") if part][-1]
    return text.lstrip("@~").strip()


def parse_page_info(body: str) -> PageInfo:
    """Read the page head once and keep the signals a profile check needs."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(body[:MAX_BODY_SCAN], "html.parser")
    title = _text(soup.title)
    description = _meta(soup, "name", "description")
    og_title = _meta(soup, "property", "og:title") or _meta(
        soup, "name", "twitter:title")
    og_description = (_meta(soup, "property", "og:description")
                      or _meta(soup, "name", "twitter:description"))
    canonical_node = soup.find("link", rel="canonical")
    canonical = ""
    if canonical_node:
        canonical = utils.clean_text(canonical_node.get("href", ""))
    og_url = _meta(soup, "property", "og:url")
    handles = tuple(
        handle for handle in (_handle_from_value(match.group(1))
                              for match in _HANDLE_JSON.finditer(
                                  body[:MAX_BODY_SCAN]))
        if handle)
    embedded_missing = bool(_EMBEDDED_MISSING.search(body[:MAX_BODY_SCAN]))
    for node in soup(["script", "style", "noscript", "template"]):
        node.decompose()
    visible = utils.clean_text(soup.get_text(" ", strip=True))
    return PageInfo(title=title, description=description, og_title=og_title,
                    og_description=og_description, canonical=canonical,
                    og_url=og_url, handles=handles, visible=visible,
                    embedded_missing=embedded_missing)


def parse_page(body: str, username: str) -> tuple[str, str]:
    info = parse_page_info(body)
    return info.title or info.og_title, info.description or info.og_description


def _visible_text(body: str) -> str:
    """Text a person can see, without scripts or link attributes.

    Scanning raw HTML would match a canonical ``href="/acme"`` on a 404 page,
    which is exactly the false positive this check exists to avoid.
    """
    return parse_page_info(body).visible


def _mentions(text: str, username: str) -> bool:
    """True when ``username`` appears as a handle, not inside another word."""
    if not text:
        return False
    pattern = (rf"(?<![{_HANDLE_CHARS}]){re.escape(username)}"
               rf"(?![{_HANDLE_CHARS}])")
    return re.search(pattern, text, re.IGNORECASE) is not None


#: Sites whose canonical/og:url is a trustworthy statement that the profile
#: exists. Their initial HTML is otherwise a generic shell. A 404 on these
#: sites omits the canonical link, which is covered by tests.
_CANONICAL_PROFILE_HOSTS = frozenset({"twitch.tv"})


def _canonical_handle(info: PageInfo) -> str:
    for value in (info.canonical, info.og_url):
        handle = _handle_from_value(value)
        if handle:
            return handle
    return ""


def _error_text(exc: Exception) -> str:
    """A useful message even when the exception has no text of its own."""
    detail = str(exc).strip()
    if not detail:
        if isinstance(exc, httpx.TimeoutException):
            detail = "timed out"
        elif isinstance(exc, httpx.ConnectError):
            detail = "could not connect"
        else:
            detail = "no response"
    return f"{type(exc).__name__}: {detail}"


async def check_one(client: httpx.AsyncClient, username: str, base: str,
                    *, timeout: float = 15.0, scan_body: bool = True) -> Hit:
    url = profile_url(base, username)
    detected = platforms.detect_profiles(url)
    details: dict[str, object] = detected[0] if detected else {}
    platform = str(details.get("platform") or platforms.host_label(url))
    category = str(details.get("category") or "")
    confidence = int(details.get("confidence") or 0)
    handle = str(details.get("handle") or username)
    try:
        response = await client.get(url, timeout=timeout,
                                    follow_redirects=True)
    except httpx.HTTPError as exc:
        return Hit(username=username, url=url, platform=platform,
                   category=category, confidence=confidence, handle=handle,
                   error=_error_text(exc))
    hit = Hit(username=username, url=str(response.url),
              status=response.status_code, platform=platform,
              category=category, confidence=confidence, handle=handle)
    if response.status_code != 200:
        return hit
    info = parse_page_info(response.text)
    hit.title = info.title or info.og_title
    hit.description = info.description or info.og_description
    # A soft 404 is a 200 page that says the account is gone. Never let a
    # footer mention of the username turn that into a "found".
    if any(marker in hit.title.casefold() for marker in _MISSING_MARKERS):
        return hit
    if info.embedded_missing:
        return hit
    # The requested URL always contains the username, so only a redirect to a
    # different address says anything about the profile. A trailing slash is
    # the same address; treating it as a redirect marked reddit.com/user/x/
    # as a profile even when the page was empty.
    requested = urllib.parse.urlsplit(url)
    final = urllib.parse.urlsplit(str(response.url))
    path_changed = final.path.rstrip("/") != requested.path.rstrip("/")
    redirected = path_changed and _mentions(final.path, username)
    if redirected:
        hit.matched, hit.match = True, "redirect"
        return hit

    signals = " ".join(part for part in (
        info.title, info.description, info.og_title, info.og_description) if part)
    if _mentions(signals, username):
        hit.matched, hit.match = True, "metadata"
        return hit

    if any(handle.casefold() == username.casefold() for handle in info.handles):
        hit.matched, hit.match = True, "structured"
        return hit

    host = (final.hostname or "").lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    canonical = _canonical_handle(info)
    if (host in _CANONICAL_PROFILE_HOSTS
            and canonical.casefold() == username.casefold()):
        hit.matched, hit.match = True, "canonical"
        return hit

    if scan_body and info.visible:
        if any(marker in info.visible.casefold()
               for marker in _BODY_MISSING_MARKERS):
            return hit
        if _mentions(info.visible, username):
            hit.matched, hit.match = True, "body"
    return hit


def _is_transport_reset(context: dict[str, object]) -> bool:
    """True for the harmless Windows proactor socket-reset callback.

    The loop reports a connection reset while closing a pooled socket as an
    unhandled callback error. The site itself is already reported through the
    normal error list; only that specific callback is silenced.
    """
    return (isinstance(context.get("exception"),
                       (ConnectionResetError, ConnectionAbortedError))
            and "connection_lost" in str(context.get("message") or ""))


async def run(username: str, platforms: Iterable[str] | None = None, *,
              concurrency: int = 8, timeout: float = 15.0,
              proxies: tuple[str, ...] = (), verify_tls: bool = True,
              use_env_proxy: bool = False,
              progress: Callable[[Hit], None] | None = None) -> UsernameReport:
    username = str(username or "").strip()
    if not username:
        raise ValueError("a username search needs a username")
    # People copy handles as @name from social sites; the at-sign is notation,
    # not part of the account name on any of the checked templates.
    if username.startswith("@"):
        username = username[1:].strip()
        if not username:
            raise ValueError("a username search needs a username")
    if not _SAFE_NAME.fullmatch(username):
        raise ValueError("usernames may only contain letters, digits, '.', '_' and '-'")
    templates = list(platforms) if platforms is not None else load_platforms()
    if not templates:
        raise ValueError("no platform URLs to check")
    # The shipped list has historical duplicates, and a custom list may too.
    # Checking the same URL twice inflated "checked" and doubled its errors.
    templates = list(dict.fromkeys(templates))

    outcome = UsernameReport(username=username)
    proxy = None
    if proxies:
        from .tools_handler import _normalize_proxy_pool

        proxy = _normalize_proxy_pool(proxies)[0]

    limits = httpx.Limits(max_connections=max(2, concurrency),
                          max_keepalive_connections=max(2, concurrency))
    headers = {"User-Agent": DEFAULT_USER_AGENT,
               "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
               "Accept-Language": "en-US,en;q=0.9"}
    semaphore = asyncio.Semaphore(max(1, concurrency))

    # Windows' proactor loop logs a full traceback when a site resets a
    # pooled socket while the client closes it (WinError 10054). The
    # library already reports that site as an error; the closing socket is
    # not news. Ignore just that callback failure and keep every other
    # loop error visible for the surrounding application.
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()

    def _ignore_reset(loop: asyncio.AbstractEventLoop,
                      context: dict[str, object]) -> None:
        if _is_transport_reset(context):
            return
        if previous_handler is not None:
            previous_handler(loop, context)
        else:
            loop.default_exception_handler(context)

    loop.set_exception_handler(_ignore_reset)
    try:
        async with httpx.AsyncClient(proxy=proxy,
                                     verify=utils.ssl_verify(verify_tls),
                                     trust_env=use_env_proxy and proxy is None,
                                     headers=headers, limits=limits,
                                     timeout=timeout) as client:
            async def worker(base: str) -> Hit:
                async with semaphore:
                    hit = await check_one(client, username, base, timeout=timeout)
                    if progress:
                        progress(hit)
                    return hit

            hits = await asyncio.gather(*(worker(base) for base in templates))
    finally:
        loop.set_exception_handler(previous_handler)
    # Best leads first, then a stable order for the rest. Duplicate final
    # addresses (two templates redirecting to one profile) are collapsed.
    ordered = sorted(hits, key=lambda hit: (
        not hit.found, -hit.confidence, hit.platform.casefold(), hit.url))
    seen: set[str] = set()
    for hit in ordered:
        key = utils.canonical_url(hit.url) or hit.url
        if key in seen:
            continue
        seen.add(key)
        outcome.hits.append(hit)
    return outcome


def run_sync(username: str, **kwargs: object) -> UsernameReport:
    return asyncio.run(run(username, **kwargs))  # type: ignore[arg-type]


def write(outcome: UsernameReport, out_dir: str | Path = "Results",
          formats: tuple[str, ...] | list[str] = ("txt", "json"),
          include_all: bool = False) -> dict[str, str]:
    if not formats:
        return {}
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    stem = report.results_path(directory, f"username-{outcome.username}", "")
    written: dict[str, str] = {}
    for name in formats:
        # ``with_suffix`` would replace the dot in a username such as
        # ``john.doe`` instead of adding the extension.
        path = stem.with_name(f"{stem.name}.{name}")
        if name == "json":
            payload: dict[str, object] = {
                "username": outcome.username,
                "started": outcome.started,
                "found": len(outcome.found),
                "checked": len(outcome.hits),
                "summary": outcome.summary(),
                "detections": outcome.detections(),
                "profiles": [asdict(hit) for hit in outcome.found],
                "errors": [asdict(hit) for hit in outcome.errors],
            }
            if include_all:
                payload["hits"] = [asdict(hit) for hit in outcome.hits]
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                            encoding="utf-8")
        elif name == "csv":
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle, fieldnames=["username", "url", "status", "title",
                                        "description", "matched", "match",
                                        "error", "platform", "category",
                                        "confidence", "handle", "source"])
                writer.writeheader()
                for hit in outcome.hits:
                    writer.writerow(asdict(hit))
        elif name == "md":
            lines = [f"# Username search: `{outcome.username}`", "",
                     f"_{outcome.started}_", "",
                     f"Checked **{len(outcome.hits)}** platforms, "
                     f"found **{len(outcome.found)}** profiles.", ""]
            detections = outcome.detections()
            if detections["leads"]:
                lines += ["## Detections", ""]
                for signal, count in detections["matched_signals"].items():
                    lines.append(
                        f"- {STATE_LABELS.get(signal, signal)}: **{count}**")
                for category, count in detections["categories"].items():
                    lines.append(f"- Category `{category}`: **{count}**")
                if detections["handles"]:
                    lines.append("- Handles: " + ", ".join(
                        f"`{handle}`" for handle in detections["handles"]))
                lines.append(f"- Verified leads: **{detections['verified']}** "
                             f"of {detections['leads']}")
                lines.append("")
            for hit in outcome.found:
                label = hit.platform or hit.url
                if hit.category:
                    label += f" ({hit.category})"
                detail = []
                if hit.handle:
                    detail.append(f"`{hit.handle}`")
                if hit.confidence:
                    detail.append(f"confidence {hit.confidence}")
                if hit.match:
                    detail.append(STATE_LABELS.get(hit.match, hit.match))
                suffix = f" - {', '.join(detail)}" if detail else ""
                lines.append(f"- [{hit.title or label}]({hit.url}) - "
                             f"{hit.status}{suffix}")
            if include_all:
                lines += ["", "## All checked", "",
                          "| Platform | Status | URL | Result |",
                          "| --- | --- | --- | --- |"]
                for hit in outcome.hits:
                    result = "found" if hit.found else (
                        hit.error.split(":", 1)[0] if hit.error else "no match")
                    lines.append(f"| {hit.platform or '-'} | {hit.status or '-'} "
                                 f"| <{hit.url}> | {result} |")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            lines = [f"Username: {outcome.username}",
                     f"Started: {outcome.started}", "=" * 78]
            for hit in outcome.found:
                lines += [f"URL: {hit.url}", f"Status: {hit.status}"]
                if hit.platform:
                    lines.append(f"Platform: {hit.platform}"
                                 + (f" ({hit.category})" if hit.category else ""))
                if hit.handle:
                    lines.append(f"Handle: {hit.handle}")
                if hit.confidence:
                    lines.append(f"Confidence: {hit.confidence}")
                if hit.title:
                    lines.append(f"Title: {hit.title}")
                if hit.description:
                    lines.append(f"Description: {hit.description}")
                if hit.match:
                    lines.append("Matched on: "
                                 f"{STATE_LABELS.get(hit.match, hit.match)}")
                lines.append("-" * 78)
            detections = outcome.detections()
            if detections["leads"]:
                lines += ["", "Detections", "=" * 78]
                for signal, count in detections["matched_signals"].items():
                    lines.append(
                        f"{STATE_LABELS.get(signal, signal)} x{count}")
                for category, count in detections["categories"].items():
                    lines.append(f"Category {category}: {count}")
                if detections["handles"]:
                    lines.append("Handles: "
                                 + ", ".join(detections["handles"]))
                lines.append(f"Verified leads: {detections['verified']} of "
                             f"{detections['leads']}")
            lines += ["", f"Found {len(outcome.found)} of {len(outcome.hits)} platforms."]
            if include_all:
                lines += ["", "All checked", "=" * 78]
                for hit in outcome.hits:
                    result = "found" if hit.found else (
                        f"error: {hit.error}" if hit.error else "no match")
                    lines.append(f"{hit.url} - HTTP {hit.status or 'no response'} - "
                                 f"{result}")
            if outcome.errors:
                lines.append(f"Errors: {len(outcome.errors)}")
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written[name] = str(path)
    return written


def settings_proxies(settings: config.Settings) -> tuple[str, ...]:
    return settings.proxies
