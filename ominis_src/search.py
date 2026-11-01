"""Run one search across the selected providers and write the report."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Callable

from . import config, engines, platforms, report, styxnet, utils

Progress = Callable[[engines.Result], None]

MAX_PAGES = 10


async def run(settings: config.Settings,
              progress: Progress | None = None) -> report.SearchReport:
    outcome = report.SearchReport(query=settings.query,
                                  engines=list(settings.engines),
                                  proxies_used=settings.proxy_enabled)
    seen: set[str] = set()
    styxnet_failed = False

    if settings.styxnet:
        styxnet_failed = not await _styxnet_pass(settings, outcome, seen,
                                                 progress)
        if styxnet_failed:
            # A rejected key or a busy service must not lose the local engines.
            outcome.engines = list(settings.engines)

    if not settings.styxnet or styxnet_failed:
        await _local_pass(settings, outcome, seen, progress)

    outcome.mentions = _mentions(outcome, settings.query)
    outcome.profiles = _profiles(outcome.profiles, outcome.records)
    return outcome


async def _styxnet_pass(settings: config.Settings, outcome: report.SearchReport,
                        seen: set[str], progress: Progress | None) -> bool:
    try:
        answer = await asyncio.to_thread(
            styxnet.search,
            settings.query,
            key=settings.styxnet_key,
            endpoint=settings.styxnet_endpoint,
            max_engines=settings.styxnet_engines,
            res_limit=settings.page_size,
            scopes=settings.styxnet_scopes,
            timeout=max(120.0, settings.timeout),
        )
    except styxnet.StyxNetError as exc:
        outcome.errors.append(f"styxnet: {exc}")
        return False

    outcome.styxnet = True
    outcome.engines = ["styxnet"]
    outcome.styxnet_meta = {
        "engines": answer.engines_used,
        "elapsed_ms": answer.elapsed_ms,
        "archive_id": answer.archive_id,
    }
    for item in answer.results:
        url = str(item.get("url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        record = report.SearchRecord(
            title=str(item.get("title") or url), url=url,
            engine="styxnet", snippet=str(item.get("snippet") or ""),
            position=len(outcome.records) + 1)
        outcome.records.append(record)
        if progress:
            progress(engines.Result(title=record.title, url=record.url,
                                    engine="styxnet", snippet=record.snippet,
                                    position=record.position))
        if len(outcome.records) >= settings.max_results:
            break
    outcome.profiles.extend(answer.profiles)
    return True


async def _local_pass(settings: config.Settings, outcome: report.SearchReport,
                      seen: set[str], progress: Progress | None) -> None:
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


def _mentions(outcome: report.SearchReport, query: str) -> dict[str, int]:
    total: Counter[str] = Counter()
    for record in outcome.records:
        text = " ".join(part for part in
                        (record.title, record.url, record.snippet) if part)
        total.update(utils.extract_mentions(text, query))
    return dict(total)


def _profiles(known: list[dict[str, object]],
              records: list[report.SearchRecord]) -> list[dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for profile in known:
        key = platforms.profile_key(profile)
        if key:
            found.setdefault(key, profile)
    for record in records:
        for profile in utils.find_social_profiles(record.url):
            key = platforms.profile_key(profile)
            if key:
                found.setdefault(key, profile)
    return [profile for profile in found.values() if profile]


def run_sync(settings: config.Settings,
             progress: Progress | None = None) -> report.SearchReport:
    return asyncio.run(run(settings, progress))


def write(outcome: report.SearchReport,
          settings: config.Settings) -> dict[str, str]:
    paths = report.write_all(outcome, settings.out_dir, settings.formats)
    return {name: str(path) for name, path in paths.items()}
