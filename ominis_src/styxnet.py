"""StyxNet search client.

``ominis search "query" --styxnet`` sends the query to WinterGate's StyxNet
service instead of scraping DuckDuckGo and Bing. StyxNet aggregates its own
engine pool and also returns the platform hits its username lane found for the
query, so the report keeps the same shape.

Only the search endpoint is used. Access is free during the preview, but a key
is required. The key is never written to a report or printed:

1. ``--styxnet-key KEY`` (highest priority)
2. ``STYXNET_ACCESS_KEY`` in the environment
3. ``OMINIS_STYXNET_KEY`` in the environment
4. ``~/.config/ominis/styxnet-key.txt`` (or ``%APPDATA%\\ominis\\...``)
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import platforms, utils

DEFAULT_ENDPOINT = "https://wintergate.org/styxnet/api"
SERVICE_URL = "https://wintergate.org/styxnet/"
KEY_ENV = "STYXNET_ACCESS_KEY"
KEY_FILE = "styxnet-key.txt"
DEFAULT_SCOPES = ("surface", "onion", "deep")

#: Client-side courtesy limits. They apply to every terminal on this machine,
#: not just the current process, and cannot be switched off from the CLI. The
#: service also enforces its own limits; these exist so a local user does not
#: accidentally flood a shared free service.
MIN_INTERVAL = 10.0          # seconds between two searches
MAX_PER_HOUR = 20            # searches in any rolling hour
MAX_PER_DAY = 100            # searches in any rolling day
MAX_ENGINES = 200            # cap one request so "mass" cannot hammer the pool
LEASE_GRACE = 30.0           # extra seconds before an abandoned lease expires
LOCK_TIMEOUT = 5.0
LOCK_STALE = 30.0

ROTATION_NOTE = (
    "StyxNet access is free during the preview, but it is rate limited. "
    "Wait for the cooldown shown above and try again."
)

ACCESS_NOTE = (
    "StyxNet access is free during the preview, but it needs a key. Join the "
    "WinterGate Discord at https://discord.gg/tu5CynxjZq and request access "
    "from AnonCatalyst, then pass --styxnet-key, set STYXNET_ACCESS_KEY, or "
    "save the key to ~/.config/ominis/styxnet-key.txt."
)

#: Result titles that mean the platform answered with an error page.
_MISSING_MARKERS = (
    "404", "not found", "page not found", "does not exist", "doesn't exist",
    "does not exits", "doesn't exits", "no longer exists",
    "no longer available", "user not found", "profile not found",
    "community :: error", "invalid address", "invalid user", "not a valid",
    "не существует", "не найден", "не найдена", "страница не найдена",
)

#: A live page can still be a login wall or a search page. These markers keep
#: the service's username lane from turning those pages into "profiles".
_GATE_MARKERS = (
    "login", "log in", "sign in", "signin", "sign up", "signup",
    "register", "registration", "create an account", "account page",
    "visitor system", "privacy gate", "one moment", "just a moment",
    "cloudflare", "access denied", "captcha", "verify you are human",
    "search results", "search for", "memberlist", "login required",
    "enable javascript", "javascript is disabled", "enter your password",
    "вход", "регистрация",
)

#: Path segments that identify site pages rather than a person's profile.
#: Only consulted when the curated registry does not already recognise the URL.
_PROFILE_RESERVED = frozenset({
    "login", "log-in", "signin", "sign-in", "signup", "sign-up",
    "register", "registration", "auth", "search", "explore", "discover",
    "settings", "help", "about", "terms", "privacy", "password", "reset",
    "verify", "captcha", "account", "accounts",
    # Subpages of a profile that StyxNet's username lane sometimes returns as
    # if they were the profile itself.
    "clips", "videos", "followers", "following", "schedule", "store",
    "posts", "media", "reels", "stories", "photos", "playlists",
    "comments", "replies",
})

_QUERY_SPLIT = re.compile(r"[^A-Za-z0-9_.-]+")


class StyxNetError(RuntimeError):
    """StyxNet could not answer; the caller decides whether to continue."""


@dataclass
class StyxNetAnswer:
    query: str
    results: list[dict[str, Any]] = field(default_factory=list)
    profiles: list[dict[str, Any]] = field(default_factory=list)
    engines_used: int = 0
    elapsed_ms: int = 0
    archive_id: str = ""


def key_candidates() -> list[Path]:
    """Places the CLI looks for a saved key, in order."""
    paths = [Path.home() / ".config" / "ominis" / KEY_FILE]
    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(Path(appdata) / "ominis" / KEY_FILE)
    return paths


def load_key(explicit: str = "") -> str:
    """Return the first key found, or an empty string."""
    if explicit and explicit.strip():
        return explicit.strip()
    for name in (KEY_ENV, "OMINIS_STYXNET_KEY"):
        environment = os.environ.get(name, "").strip()
        if environment:
            return environment
    for path in key_candidates():
        try:
            value = path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if value:
            return value
    return ""


def _check_key(key: str) -> str:
    value = (key or "").strip()
    if not value:
        raise StyxNetError(ACCESS_NOTE)
    if not value.startswith("sgn_"):
        raise StyxNetError(
            "that does not look like a StyxNet access key (expected sgn_...); "
            + ACCESS_NOTE)
    return value


def _text(value: Any) -> str:
    """Decode entities and strip invisible padding from remote text."""
    return utils.clean_text(value)


def _number(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _clean_url(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    url = value.strip()
    return url if url.startswith(("http://", "https://")) else ""


def _looks_missing(title: str, description: str) -> bool:
    text = f"{title} {description}".casefold()
    return any(marker in text for marker in _MISSING_MARKERS)


def _looks_gated(title: str, description: str) -> bool:
    text = f"{title} {description}".casefold()
    return any(marker in text for marker in _GATE_MARKERS)


def _mentions_query(text: str, query: str) -> bool:
    """True when a word from the query appears as a whole word."""
    if not text or not query:
        return False
    for token in _QUERY_SPLIT.split(str(query)):
        if len(token) < 3:
            continue
        pattern = (rf"(?<![A-Za-z0-9_.-]){re.escape(token)}"
                   rf"(?![A-Za-z0-9_.-])")
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _reserved_path(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path.casefold()
    segments = {part for part in re.split(r"[^a-z0-9-]+", path) if part}
    return bool(segments & _PROFILE_RESERVED)


def _tail_mentions_query(url: str, query: str) -> bool:
    """True when the URL ends with the query, not a subpage such as ``/clips``.

    StyxNet's username lane sometimes labels a channel subpage as the channel
    itself. A real profile URL normally ends with the handle, so the last path
    segment (or a query value) must contain one of the query's words.
    """
    parts = urllib.parse.urlsplit(url)
    segments = [part for part in parts.path.split("/") if part]
    tail = " ".join(segments[-1:] +
                    [value for _, value in urllib.parse.parse_qsl(parts.query)])
    normalized = re.sub(r"[^a-z0-9]", "", tail.casefold())
    if not normalized:
        return False
    for token in _QUERY_SPLIT.split(str(query)):
        token = re.sub(r"[^a-z0-9]", "", token.casefold())
        if len(token) >= 3 and token in normalized:
            return True
    return False


def _credible_profile(item: dict[str, Any], query: str) -> dict[str, Any] | None:
    """Validate one StyxNet username candidate before trusting it.

    The service's search response includes a username lane that can return
    login walls, site search pages, and human/bot 404s. A candidate is kept
    only when the URL is a known profile shape and its visible text mentions
    the query, or when the text clearly names the query on a non-reserved URL.
    """
    url = _clean_url(item.get("url"))
    if not url:
        return None
    if _number(item.get("status")) >= 400:
        return None
    title = _text(item.get("title"))
    description = _text(item.get("meta_description")
                        or item.get("description") or "")
    if _looks_missing(title, description) or _looks_gated(title, description):
        return None
    if not _mentions_query(f"{title} {description}", query):
        return None

    detected = platforms.detect_profiles(url)
    if detected:
        chosen = detected[0]
        return {
            "platform": str(chosen.get("platform") or "StyxNet"),
            "profile_url": str(chosen.get("profile_url") or url),
            "category": str(chosen.get("category") or "other"),
            "confidence": _number(chosen.get("confidence")) or 50,
            "title": title,
            "source": "styxnet",
        }

    if _reserved_path(url):
        return None
    if not _tail_mentions_query(url, query):
        return None
    confidence = _number(item.get("confidence")) or 40
    return {
        "platform": _text(item.get("platform")) or "StyxNet",
        "profile_url": utils.canonical_url(url) or url,
        "category": _text(item.get("category")) or "other",
        # The service's label is not independently verified, so cap it.
        "confidence": min(confidence, 60),
        "title": title,
        "source": "styxnet",
    }


def _normalise_results(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    results: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        url = _clean_url(item.get("url") or item.get("link"))
        if not url:
            continue
        title = _text(item.get("title") or item.get("name") or url)
        description = _text(item.get("description") or item.get("snippet") or "")
        results.append({
            "title": title,
            "url": url,
            "snippet": description,
            "engine": str(item.get("engine") or "styxnet"),
            "platform": str(item.get("platform") or ""),
            "confidence": item.get("confidence") or item.get("_confidence") or "",
            "category": str(item.get("category") or ""),
        })
    return results


def _normalise_profiles(payload: Any,
                        query: str = "") -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []
    profiles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue
        profile = _credible_profile(item, query)
        if not profile:
            continue
        key = platforms.profile_key(profile)
        if key in seen:
            continue
        seen.add(key)
        profiles.append(profile)
    # A caller that prints the answer directly should see the strongest lead
    # first, exactly like the search report does.
    profiles.sort(key=lambda profile: (
        -_number(profile.get("confidence")),
        str(profile.get("platform") or "").casefold(),
        str(profile.get("profile_url") or "")))
    return profiles


def _request(client: httpx.Client, method: str, path: str,
             **kwargs: Any) -> httpx.Response:
    last: Exception | None = None
    for attempt in range(2):
        try:
            response = client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            last = exc
        else:
            if response.status_code < 500:
                return response
            last = StyxNetError(f"StyxNet returned HTTP {response.status_code}")
        if attempt == 0:
            time.sleep(2)
    raise StyxNetError(f"StyxNet request failed: {last}") from None


class StyxNetRateLimited(StyxNetError):
    """A local courtesy limit said no; ``retry_after`` is in seconds."""

    def __init__(self, message: str, retry_after: float = 0.0) -> None:
        super().__init__(message)
        self.retry_after = max(0, int(round(retry_after)))


def _state_dir() -> Path:
    override = os.environ.get("OMINIS_STYXNET_STATE_DIR", "").strip()
    return Path(override) if override else Path.home() / ".config" / "ominis"


def _state_paths() -> tuple[Path, Path, Path]:
    directory = _state_dir()
    return (directory, directory / "styxnet-usage.json",
            directory / "styxnet.lock")


class _Lock:
    """A small cross-process lock that works on Windows and POSIX."""

    def __init__(self, path: Path, timeout: float = LOCK_TIMEOUT) -> None:
        self.path = path
        self.timeout = timeout
        self.held = False

    def __enter__(self) -> "_Lock":
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                descriptor = os.open(self.path,
                                     os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    age = time.time() - os.path.getmtime(self.path)
                except OSError:
                    age = 0.0
                if age > LOCK_STALE:
                    try:
                        os.unlink(self.path)
                    except OSError:
                        pass
                    continue
                if time.monotonic() >= deadline:
                    raise StyxNetError(
                        "another StyxNet request is starting; try again in a "
                        "moment") from None
                time.sleep(0.05)
            else:
                os.close(descriptor)
                self.held = True
                return self

    def __exit__(self, *exc_info: object) -> None:
        if self.held:
            try:
                os.unlink(self.path)
            except OSError:
                pass
            self.held = False


def _read_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"requests": [], "lease": None}
    if not isinstance(data, dict):
        return {"requests": [], "lease": None}
    requests = [float(value) for value in data.get("requests", [])
                if isinstance(value, (int, float))]
    lease = data.get("lease")
    return {"requests": requests,
            "lease": lease if isinstance(lease, dict) else None}


def _write_state(path: Path, state: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    os.replace(temporary, path)


def _reserve_slot(timeout: float) -> str:
    """Reserve one search slot, sharing the quota across every terminal."""
    directory, state_path, lock_path = _state_paths()
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StyxNetError(
            f"cannot create the StyxNet state directory {directory}: {exc}"
        ) from None
    with _Lock(lock_path):
        state = _read_state(state_path)
        now = time.time()
        requests = [value for value in state["requests"] if now - value < 86400]
        lease = state.get("lease") or {}
        expires = float(lease.get("expires") or 0) if isinstance(lease, dict) else 0
        if expires > now:
            raise StyxNetRateLimited(
                "another StyxNet search is already running on this machine; "
                "wait for it to finish", expires - now)
        if requests:
            wait = MIN_INTERVAL - (now - max(requests))
            if wait > 0:
                raise StyxNetRateLimited(
                    f"StyxNet cooldown: wait {int(wait) + 1}s before the next "
                    "search", wait)
        last_hour = [value for value in requests if now - value < 3600]
        if len(last_hour) >= MAX_PER_HOUR:
            raise StyxNetRateLimited(
                f"StyxNet hourly limit reached ({MAX_PER_HOUR}/hour); wait for "
                "the window to roll over",
                3600 - (now - min(last_hour)))
        if len(requests) >= MAX_PER_DAY:
            raise StyxNetRateLimited(
                f"StyxNet daily limit reached ({MAX_PER_DAY}/day); wait for the "
                "window to roll over",
                86400 - (now - min(requests)))
        lease_id = uuid.uuid4().hex
        requests.append(now)
        _write_state(state_path, {
            "requests": requests,
            "lease": {
                "id": lease_id,
                "pid": os.getpid(),
                "expires": now + max(30.0, float(timeout)) + LEASE_GRACE,
            },
        })
    return lease_id


def _release_slot(lease_id: str) -> None:
    directory, state_path, lock_path = _state_paths()
    try:
        with _Lock(lock_path, timeout=2.0):
            state = _read_state(state_path)
            lease = state.get("lease") or {}
            if isinstance(lease, dict) and lease.get("id") == lease_id:
                state["lease"] = None
                _write_state(state_path, state)
    except (OSError, StyxNetError):
        # A leftover lease expires by itself; never hide the real error.
        pass


def search(query: str, *, key: str = "", endpoint: str = DEFAULT_ENDPOINT,
           max_engines: int = 35, res_limit: int = 50,
           scopes: tuple[str, ...] | list[str] = DEFAULT_SCOPES,
           timeout: float = 120.0, use_env_proxy: bool = False) -> StyxNetAnswer:
    """Run one StyxNet search and return normalised results and profiles."""
    query = str(query or "").strip()
    if not query:
        raise StyxNetError("a StyxNet search needs a query")
    if not 1 <= int(max_engines) <= MAX_ENGINES:
        raise StyxNetError(f"max_engines must be between 1 and {MAX_ENGINES}")
    if int(res_limit) < 1:
        raise StyxNetError("res_limit must be at least 1")
    chosen_scopes = [scope for scope in scopes if scope]
    if not chosen_scopes:
        raise StyxNetError("choose at least one StyxNet scope")

    body = {
        "query": query,
        "scopes": chosen_scopes,
        "advanced": {},
        "max_engines": int(max_engines),
        "save": False,
        "res_limit": int(res_limit),
    }
    headers = {
        "Authorization": "Bearer " + _check_key(key),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    lease = _reserve_slot(timeout)
    try:
        with httpx.Client(base_url=endpoint.rstrip("/"), headers=headers,
                          timeout=timeout, follow_redirects=True,
                          verify=utils.ssl_verify(),
                          trust_env=use_env_proxy) as client:
            response = _request(client, "POST", "/search", json=body)
    except httpx.HTTPError as exc:
        raise StyxNetError(f"StyxNet request failed: {exc}") from None
    finally:
        _release_slot(lease)

    if response.status_code in (401, 403):
        raise StyxNetError(
            "StyxNet rejected the access key. Check it has not been revoked; "
            + ACCESS_NOTE)
    if response.status_code >= 400:
        raise StyxNetError(f"StyxNet returned HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError:
        raise StyxNetError("StyxNet returned a non-JSON response") from None
    if not isinstance(payload, dict):
        raise StyxNetError("StyxNet returned an unexpected response")

    engines = payload.get("engines_used") or []
    archive = payload.get("archive") or {}
    if isinstance(engines, list):
        engines_used = len(engines)
    else:
        engines_used = _number(engines)
    return StyxNetAnswer(
        query=str(payload.get("query") or query),
        results=_normalise_results(payload.get("results")),
        profiles=_normalise_profiles(payload.get("username_results"), query),
        engines_used=engines_used,
        elapsed_ms=int(payload.get("elapsed_ms") or 0),
        archive_id=str(archive.get("id") or "") if isinstance(archive, dict) else "",
    )
