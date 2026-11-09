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

#: Human labels for page evidence. The workstation uses the same words, so the
#: console, TXT and Markdown reports describe a detection the same way.
SIGNAL_LABELS = {
    "redirect": "Redirect",
    "canonical": "Canonical URL",
    "structured": "Structured data",
    "metadata": "Page metadata",
    "body": "Page content",
    "url": "URL pattern",
    "registry": "Platform registry",
    "styxnet": "StyxNet candidate",
    "error": "Request error",
    "checked": "No match",
}

#: The workstation groups leads by strength; the CLI reports the same buckets.
SIGNAL_STRENGTH = {
    "redirect": "strong",
    "canonical": "strong",
    "structured": "strong",
    "metadata": "strong",
    "body": "medium",
    "url": "medium",
    "registry": "medium",
    "styxnet": "candidate",
    "error": "error",
    "checked": "none",
    "": "none",
}


def _profile_strength(profile: dict[str, object]) -> str:
    source = str(profile.get("source") or "")
    if source in SIGNAL_STRENGTH:
        return SIGNAL_STRENGTH[source]
    # A lead with a profile URL but no recorded source is a URL-shape lead,
    # which the workstation ranks as medium rather than unconfirmed.
    if profile.get("profile_url"):
        return "medium"
    return "strong" if profile.get("verified") else "none"


def _tally(values: object) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:  # type: ignore[union-attr]
        key = str(value or "").strip()
        if key:
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


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
    #: Page-level evidence, filled by the optional scan pass. A search
    #: snippet is a claim; these fields say what the page itself proved.
    status: int = 0
    final_url: str = ""
    signal: str = ""
    detail: str = ""
    matched: bool = False
    scanned: bool = False
    platform: str = ""
    #: Detection depth carried alongside the platform: the platform category,
    #: the detector's confidence, and the handle the URL rules read.
    category: str = ""
    confidence: int = 0
    handle: str = ""
    page_title: str = ""
    page_description: str = ""
    error: str = ""


@dataclass
class SearchReport:
    query: str
    started: str = field(default_factory=lambda: datetime.now(timezone.utc)
                         .isoformat(timespec="seconds"))
    records: list[SearchRecord] = field(default_factory=list)
    mentions: dict[str, int] = field(default_factory=dict)
    profiles: list[dict[str, object]] = field(default_factory=list)
    engines: list[str] = field(default_factory=list)
    proxies_used: bool = False
    styxnet: bool = False
    styxnet_meta: dict[str, object] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def detections(self) -> dict[str, object]:
        """Roll up what the scan proved and what the platform rules found.

        This is the same depth the workstation shows in its detection line:
        which signals confirmed a page, how many leads were verified, the
        categories they belong to, and the handles that were read from them.
        """
        scanned = [record for record in self.records if record.scanned]
        handles = sorted({
            str(profile.get("handle") or "")
            for profile in self.profiles
        } - {""})
        profile_urls = {
            str(profile.get("profile_url") or "").rstrip("/").casefold()
            for profile in self.profiles
        } - {""}

        def resolved(record: SearchRecord) -> bool:
            for url in (record.url, record.final_url):
                if str(url or "").rstrip("/").casefold() in profile_urls:
                    return True
            return False

        return {
            "signals": _tally(record.signal for record in scanned),
            "matched_signals": _tally(record.signal for record in scanned
                                      if record.matched),
            "sources": _tally(profile.get("source")
                              for profile in self.profiles),
            "strengths": _tally(_profile_strength(profile)
                                for profile in self.profiles),
            "categories": _tally(profile.get("category")
                                 for profile in self.profiles),
            "platforms": _tally(profile.get("platform")
                                for profile in self.profiles),
            "handles": handles,
            "leads": len(self.profiles),
            "verified": sum(1 for profile in self.profiles
                            if profile.get("verified")),
            "resolved": sum(1 for record in self.records if resolved(record)),
        }

    def summary(self) -> dict[str, object]:
        summary: dict[str, object] = {
            "query": self.query,
            "started": self.started,
            "results": len(self.records),
            "mentions": self.mentions,
            "profiles": len(self.profiles),
            "engines": self.engines,
            "proxies_used": self.proxies_used,
            "styxnet": self.styxnet,
            "scanned": sum(1 for record in self.records if record.scanned),
            "page_matches": sum(1 for record in self.records
                                if record.scanned and record.matched),
            "detections": self.detections(),
            "errors": self.errors,
        }
        if self.styxnet_meta:
            summary["styxnet_meta"] = self.styxnet_meta
        return summary


def write_json(report: SearchReport, path: Path) -> Path:
    path.write_text(json.dumps({
        "summary": report.summary(),
        "detections": report.detections(),
        "results": [asdict(record) for record in report.records],
        "profiles": report.profiles,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_csv(report: SearchReport, path: Path) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["title", "url", "engine", "snippet", "position",
                                "status", "final_url", "signal", "detail",
                                "matched", "scanned", "platform", "category",
                                "confidence", "handle", "page_title",
                                "page_description", "error"])
        writer.writeheader()
        for record in report.records:
            writer.writerow(asdict(record))
    return path


def write_txt(report: SearchReport, path: Path) -> Path:
    lines = [f"Query: {report.query}", f"Started: {report.started}", "=" * 78]
    for record in report.records:
        lines.append(f"[{record.engine or 'search'}] {record.title}")
        lines.append(f"URL: {record.url}")
        if record.final_url and record.final_url.rstrip("/") != record.url.rstrip("/"):
            lines.append(f"Resolved: {record.final_url}")
        if record.status:
            lines.append(f"HTTP: {record.status}")
        if record.platform:
            lines.append(f"Platform: {record.platform}"
                         + (f" ({record.category})" if record.category else ""))
        if record.handle:
            lines.append(f"Handle: {record.handle}")
        if record.confidence:
            lines.append(f"Confidence: {record.confidence}")
        if record.signal:
            lines.append(f"Signal: {SIGNAL_LABELS.get(record.signal, record.signal)}")
        if record.matched:
            lines.append("Verified: yes")
        if record.detail:
            lines.append(f"Detail: {record.detail}")
        if record.error:
            lines.append(f"Error: {record.error}")
        if record.snippet:
            lines.append(f"Snippet: {record.snippet}")
        lines.append("-" * 78)
    lines.append("")
    lines.append("Summary")
    lines.append("-" * 30)
    lines.append(f"Total results: {len(report.records)}")
    lines.append(f"Unique mentions: {len(report.mentions)}")
    lines.append(f"Social profiles: {len(report.profiles)}")
    if report.styxnet:
        lines.append("Source: StyxNet"
                     + (f" ({report.styxnet_meta.get('engines')} engine(s), "
                        f"{report.styxnet_meta.get('elapsed_ms')} ms)"
                        if report.styxnet_meta else ""))
    detections = report.detections()
    if detections["matched_signals"] or detections["leads"]:
        lines.append("")
        lines.append("Detections")
        lines.append("-" * 30)
        for signal, count in detections["matched_signals"].items():
            lines.append(f"{SIGNAL_LABELS.get(signal, signal)} x{count}")
        for category, count in detections["categories"].items():
            lines.append(f"Category {category}: {count}")
        if detections["handles"]:
            lines.append("Handles: " + ", ".join(detections["handles"]))
        if detections["strengths"]:
            lines.append("Lead strength: " + ", ".join(
                f"{name} {count}"
                for name, count in detections["strengths"].items()))
        lines.append(f"Verified leads: {detections['verified']} of "
                     f"{detections['leads']}")
        if report.records:
            lines.append("Results resolving to a profile: "
                         f"{detections['resolved']} of {len(report.records)}")
    if report.profiles:
        lines.append("")
        lines.append("Detected platforms")
        lines.append("-" * 30)
        for profile in report.profiles:
            category = str(profile.get("category") or "other")
            confidence = profile.get("confidence")
            suffix = f" (confidence {confidence})" if confidence else ""
            lines.append(f"{profile.get('platform')} [{category}]{suffix}")
            lines.append(f"  {profile.get('profile_url')}")
            handle = str(profile.get("handle") or "")
            if handle:
                lines.append(f"  Handle: {handle}")
            title = str(profile.get("title") or "")
            if title:
                lines.append(f"  Title: {title}")
            source = str(profile.get("source") or "")
            if source:
                lines.append(f"  Source: {source}")
            if profile.get("verified"):
                lines.append("  Verified: yes")
            if profile.get("status"):
                lines.append(f"  HTTP: {profile.get('status')}")
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
        if record.final_url and record.final_url.rstrip("/") != record.url.rstrip("/"):
            lines.append(f"  Resolved: <{record.final_url}>  ")
        if record.platform:
            lines.append(f"  Platform: **{record.platform}**"
                         + (f" `{record.category}`" if record.category else "")
                         + "  ")
        if record.handle:
            lines.append(f"  Handle: `{record.handle}`  ")
        if record.confidence:
            lines.append(f"  Confidence: **{record.confidence}**  ")
        if record.signal:
            lines.append(f"  Signal: **{SIGNAL_LABELS.get(record.signal, record.signal)}**  ")
        if record.matched:
            lines.append("  Verified: **yes**  ")
        if record.detail:
            lines.append(f"  {record.detail}  ")
        if record.error:
            lines.append(f"  Error: {record.error}  ")
        if record.snippet:
            lines.append(f"  {record.snippet}")
        lines.append(f"  _{record.engine}_")
    lines += ["", "## Summary", "",
              f"- Results: **{len(report.records)}**",
              f"- Social profiles: **{len(report.profiles)}**"]
    if report.styxnet:
        meta = report.styxnet_meta
        source = "StyxNet"
        if meta:
            source += (f" ({meta.get('engines')} engine(s), "
                       f"{meta.get('elapsed_ms')} ms)")
        lines.append(f"- Source: **{source}**")
    if report.mentions:
        lines.append("- Mentions: " + ", ".join(
            f"`{name}` x{count}" for name, count in report.mentions.items()))
    detections = report.detections()
    if detections["matched_signals"] or detections["leads"]:
        lines += ["", "## Detections", ""]
        for signal, count in detections["matched_signals"].items():
            lines.append(f"- {SIGNAL_LABELS.get(signal, signal)}: **{count}**")
        for category, count in detections["categories"].items():
            lines.append(f"- Category `{category}`: **{count}**")
        if detections["handles"]:
            lines.append("- Handles: " + ", ".join(
                f"`{handle}`" for handle in detections["handles"]))
        if detections["strengths"]:
            lines.append("- Lead strength: " + ", ".join(
                f"{name} **{count}**"
                for name, count in detections["strengths"].items()))
        lines.append(f"- Verified leads: **{detections['verified']}** of "
                     f"{detections['leads']}")
        if report.records:
            lines.append(f"- Results resolving to a profile: "
                         f"**{detections['resolved']}** of "
                         f"{len(report.records)}")
    if report.profiles:
        lines += ["", "## Detected platforms", ""]
        for profile in report.profiles:
            category = str(profile.get("category") or "other")
            confidence = profile.get("confidence")
            suffix = f" _(confidence {confidence})_" if confidence else ""
            title = str(profile.get("title") or "")
            source = str(profile.get("source") or "")
            handle = str(profile.get("handle") or "")
            label = f" ({source})" if source else ""
            if handle:
                label += f" `{handle}`"
            url = profile.get("profile_url")
            if title:
                lines.append(
                    f"- **{profile.get('platform')}** `{category}` "
                    f"[{title}]({url}){label}{suffix}")
            else:
                lines.append(
                    f"- **{profile.get('platform')}** `{category}` "
                    f"<{url}>{label}{suffix}")
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
    if not formats:
        return {}
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name in formats:
        writer = _WRITERS.get(name)
        if writer is None:
            raise ValueError(f"unknown output format: {name}")
        written[name] = writer(report, results_path(directory, report.query, name))
    return written
