"""Run one search across the selected providers and write the report."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Callable

from . import config, engines, report, utils

Progress = Callable[[engines.Result], None]

MAX_PAGES = 10


async def run(settings: config.Settings, progress: Progress | None = None) -> report.SearchReport:
    outcome = report.SearchReport(query=settings.query,
                                  engines=list(settings.engines),
                                  proxies_used=settings.proxy_enabled)
    seen: set[str] = set()

    for engine in settings.engines:
        if engine == "serpbase" and not settings.serpbase_key:
            outcome.errors.append(
                "SerpBase was selected but no API key is set; set SERPBASE_API_KEY")
            continue
        page = 1
        while len(outcome.records) < settings.max_results and page <= MAX_PAGES:
            try:
                batch = await engines.fetch_engine(engine, settings, page)
            except Exception as exc:  # one provider must not sink the run
                outcome.errors.append(f"{engine}: {exc}")
                break
            if not batch:
                break
            added = 0
            for item in batch:
                if item.url in seen:
                    continue
                seen.add(item.url)
                outcome.records.append(report.SearchRecord(
                    title=item.title, url=item.url, engine=item.engine,
                    snippet=item.snippet, position=len(outcome.records) + 1))
                added += 1
                if progress:
                    progress(item)
                if len(outcome.records) >= settings.max_results:
                    break
            if not added:
                break
            page += 1

    outcome.mentions = _mentions(outcome, settings.query)
    outcome.profiles = _profiles(outcome.records)
    return outcome


def _mentions(outcome: report.SearchReport, query: str) -> dict[str, int]:
    total: Counter[str] = Counter()
    for record in outcome.records:
        text = " ".join(part for part in
                        (record.title, record.url, record.snippet) if part)
        total.update(utils.extract_mentions(text, query))
    return dict(total)


def _profiles(records: list[report.SearchRecord]) -> list[dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for record in records:
        for profile in utils.find_social_profiles(record.url):
            found.setdefault(profile["profile_url"], profile)
    return list(found.values())


def run_sync(settings: config.Settings, progress: Progress | None = None) -> report.SearchReport:
    return asyncio.run(run(settings, progress))


def write(outcome: report.SearchReport, settings: config.Settings) -> dict[str, str]:
    paths = report.write_all(outcome, settings.out_dir, settings.formats)
    return {name: str(path) for name, path in paths.items()}
