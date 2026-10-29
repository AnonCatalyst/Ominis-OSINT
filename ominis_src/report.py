"""Result files that are safe to name after a user's query.

A query is free text, and it used to become a file name directly, so
``../../notes`` or ``report:2026`` could escape the results folder or fail on
Windows. Names are slugged here, and every writer goes through this module.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def slug(text: str, limit: int = 60) -> str:
    """A filesystem-safe stem: no separators, no traversal, no reserved names."""
    cleaned = _UNSAFE.sub("-", str(text or "")).strip("-._ ")
    cleaned = cleaned[:limit].strip("-._ ")
    if not cleaned or cleaned.upper().split(".")[0] in _WINDOWS_RESERVED:
        cleaned = f"results-{cleaned}" if cleaned else "results"
    return cleaned


def results_path(out_dir: str | Path, query: str, suffix: str) -> Path:
    """``out_dir/<slug(query)>.<ext>`` or ``<slug>-<name>.ext``."""
    suffix = suffix.strip("-.")
    if not suffix:
        name = slug(query)
    elif "." in suffix:
        name = f"{slug(query)}-{suffix}"
    else:
        name = f"{slug(query)}.{suffix}"
    return Path(out_dir) / name


@dataclass
class SearchRecord:
    title: str
    url: str
    engine: str = ""
    snippet: str = ""
    position: int = 0


@dataclass
class SearchReport:
    query: str
    started: str = field(default_factory=lambda: datetime.now(timezone.utc)
                         .isoformat(timespec="seconds"))
    records: list[SearchRecord] = field(default_factory=list)
    mentions: dict[str, int] = field(default_factory=dict)
    profiles: list[dict[str, str]] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)
    proxies_used: bool = False
    errors: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        return {
            "query": self.query,
            "started": self.started,
            "results": len(self.records),
            "mentions": self.mentions,
            "profiles": len(self.profiles),
            "engines": self.engines,
            "proxies_used": self.proxies_used,
            "errors": self.errors,
        }


def write_json(report: SearchReport, path: Path) -> Path:
    path.write_text(json.dumps({
        "summary": report.summary(),
        "results": [asdict(record) for record in report.records],
        "profiles": report.profiles,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_csv(report: SearchReport, path: Path) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["title", "url", "engine", "snippet", "position"])
        writer.writeheader()
        for record in report.records:
            writer.writerow(asdict(record))
    return path


def write_txt(report: SearchReport, path: Path) -> Path:
    lines = [f"Query: {report.query}", f"Started: {report.started}", "=" * 78]
    for record in report.records:
        lines.append(f"[{record.engine or 'search'}] {record.title}")
        lines.append(f"URL: {record.url}")
        if record.snippet:
            lines.append(f"Snippet: {record.snippet}")
        lines.append("-" * 78)
    lines.append("")
    lines.append("Summary")
    lines.append("-" * 30)
    lines.append(f"Total results: {len(report.records)}")
    lines.append(f"Unique mentions: {len(report.mentions)}")
    lines.append(f"Social profiles: {len(report.profiles)}")
    if report.errors:
        lines.append("Errors:")
        lines.extend(f"  {error}" for error in report.errors)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_markdown(report: SearchReport, path: Path) -> Path:
    lines = [f"# Ominis search: `{report.query}`", "",
             f"_{report.started}_", ""]
    for record in report.records:
        lines.append(f"- **{record.title or record.url}**  ")
        lines.append(f"  {record.url}  ")
        if record.snippet:
            lines.append(f"  {record.snippet}")
        lines.append(f"  _{record.engine}_")
    lines += ["", "## Summary", "",
              f"- Results: **{len(report.records)}**",
              f"- Social profiles: **{len(report.profiles)}**"]
    if report.mentions:
        lines.append("- Mentions: " + ", ".join(
            f"`{name}` x{count}" for name, count in report.mentions.items()))
    if report.errors:
        lines += ["", "## Errors", ""]
        lines.extend(f"- {error}" for error in report.errors)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


_WRITERS = {
    "txt": write_txt,
    "json": write_json,
    "csv": write_csv,
    "md": write_markdown,
}


def write_all(report: SearchReport, out_dir: str | Path,
              formats: tuple[str, ...] | list[str] = ("txt", "json")) -> dict[str, Path]:
    """Write the requested formats and return ``format -> path``."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name in formats:
        writer = _WRITERS.get(name)
        if writer is None:
            raise ValueError(f"unknown output format: {name}")
        written[name] = writer(report, results_path(directory, report.query, name))
    return written
