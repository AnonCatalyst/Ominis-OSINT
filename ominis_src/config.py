"""Runtime settings for Ominis.

Everything here is explicit and local. Two rules shape the defaults:

* Proxies are opt-in. A first run must be able to search without harvesting,
  validating, or trusting a third-party proxy list.
* A setting comes from an argument first, then the environment, then the
  defaults below. Nothing is read from a file the tool writes itself.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path

DEFAULT_ENGINES = ("duckduckgo", "bing")
SERP_ENGINES = ("duckduckgo", "bing", "serpbase")

#: Where the SerpBase-compatible Google results API lives. Override when a
#: self-hosted or regional endpoint is in use.
SERPBASE_ENDPOINT = "https://api.serpbase.dev/google/search"

OUTPUT_FORMATS = ("txt", "json", "csv", "md")


def _split(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(",") if part.strip())


def parse_date(value: str | None) -> str:
    """Return ``YYYY-MM-DD`` or raise ``ValueError``.

    The scrapers accept a date range as ``df=YYYY-MM-DD..YYYY-MM-DD``; keeping
    one canonical form means the CLI, the environment and the API agree.
    """
    if not value:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    from datetime import date

    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        raise ValueError(f"not a date in YYYY-MM-DD form: {value!r}") from None


def parse_engines(value: str | tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    if isinstance(value, str):
        chosen = _split(value)
    elif value:
        chosen = tuple(str(item).strip() for item in value if str(item).strip())
    else:
        chosen = DEFAULT_ENGINES
    unknown = [item for item in chosen if item not in SERP_ENGINES]
    if unknown:
        raise ValueError(
            f"unknown engine(s): {', '.join(unknown)} "
            f"(choose from {', '.join(SERP_ENGINES)})")
    return chosen or DEFAULT_ENGINES


@dataclass(frozen=True)
class Settings:
    """One search run, fully described."""

    query: str
    engines: tuple[str, ...] = DEFAULT_ENGINES
    language: str = ""
    country: str = ""
    since: str = ""
    until: str = ""
    max_results: int = 50
    proxies: tuple[str, ...] = ()
    serpbase_key: str = ""
    out_dir: Path = field(default_factory=lambda: Path("Results"))
    formats: tuple[str, ...] = ("txt", "json")
    timeout: float = 15.0
    verify_tls: bool = True
    user_agent: str = ""

    def __post_init__(self) -> None:
        if not str(self.query or "").strip():
            raise ValueError("a search needs a query")
        if not 1 <= int(self.max_results) <= 1000:
            raise ValueError("max_results must be between 1 and 1000")
        if float(self.timeout) <= 0:
            raise ValueError("timeout must be positive")
        unknown = [name for name in self.formats if name not in OUTPUT_FORMATS]
        if unknown:
            raise ValueError(f"unknown output format(s): {', '.join(unknown)}")

    @property
    def proxy_enabled(self) -> bool:
        return bool(self.proxies)

    @property
    def page_size(self) -> int:
        """Results to ask each engine for, before de-duplication."""
        return max(10, min(200, self.max_results))

    def extended(self, **changes: object) -> "Settings":
        return replace(self, **changes)

    @classmethod
    def from_env(cls, query: str, **overrides: object) -> "Settings":
        """Build settings from ``OMINIS_*`` variables, then apply overrides."""
        base: dict[str, object] = {
            "query": query,
            "engines": parse_engines(os.environ.get("OMINIS_ENGINES")),
            "language": os.environ.get("OMINIS_LANGUAGE", ""),
            "country": os.environ.get("OMINIS_COUNTRY", ""),
            "since": parse_date(os.environ.get("OMINIS_SINCE")),
            "until": parse_date(os.environ.get("OMINIS_UNTIL")),
            "max_results": int(os.environ.get("OMINIS_MAX_RESULTS", "50")),
            "proxies": _split(os.environ.get("OMINIS_PROXY_POOL")),
            "serpbase_key": os.environ.get("SERPBASE_API_KEY", "")
            or os.environ.get("OMINIS_SERPBASE_KEY", ""),
            "out_dir": Path(os.environ.get("OMINIS_OUTPUT_DIR", "Results")),
            "formats": _split(os.environ.get("OMINIS_FORMATS")) or ("txt", "json"),
            "timeout": float(os.environ.get("OMINIS_TIMEOUT", "15")),
            "user_agent": os.environ.get("OMINIS_USER_AGENT", ""),
        }
        base.update({key: value for key, value in overrides.items()
                     if value is not None})
        return cls(**base)  # type: ignore[arg-type]


def load_proxy_file(path: str | Path) -> tuple[str, ...]:
    """Read one endpoint per line; blank lines and ``#`` comments are ignored."""
    file = Path(path).expanduser()
    if not file.is_file():
        raise ValueError(f"no proxy file at {file}")
    entries: list[str] = []
    for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    return tuple(entries)
