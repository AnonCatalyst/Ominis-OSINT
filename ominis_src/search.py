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
    seen: dict[str, report.SearchRecord] = {}
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


def _add(outcome: report.SearchReport,
         seen: dict[str, report.SearchRecord],
         record: report.SearchRecord,
         progress: Progress | None) -> bool:
    """Add a result once; merge engines and missing text for duplicates."""
    key = utils.canonical_url(record.url) or record.url
    existing = seen.get(key)
    if existing is not None:
        for engine in record.engine.split(","):
            if engine and engine not in existing.engine.split(","):
                existing.engine = (f"{existing.engine},{engine}"
                                   if existing.engine else engine)
        if not existing.snippet and record.snippet:
            existing.snippet = record.snippet
        if not existing.title and record.title:
            existing.title = record.title
        return False
    record.position = len(outcome.records) + 1
    seen[key] = record
    outcome.records.append(record)
    if progress:
        progress(engines.Result(title=record.title, url=record.url,
                                engine=record.engine, snippet=record.snippet,
                                position=record.position))
    return True


async def _styxnet_pass(settings: config.Settings, outcome: report.SearchReport,
                        seen: dict[str, report.SearchRecord],
                        progress: Progress | None) -> bool:
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
        if not url or engines.is_noise_url(url):
            continue
        _add(outcome, seen, report.SearchRecord(
            title=str(item.get("title") or url), url=url,
            engine="styxnet", snippet=str(item.get("snippet") or "")),
            progress)
        if len(outcome.records) >= settings.max_results:
            break
    outcome.profiles.extend(answer.profiles)
    return True


async def _local_pass(settings: config.Settings, outcome: report.SearchReport,
                      seen: dict[str, report.SearchRecord],
                      progress: Progress | None) -> None:
    active: list[str] = []
    for engine in settings.engines:
        if engine == "serpbase" and not settings.serpbase_key:
            outcome.errors.append(
                "SerpBase was selected but no API key is set; set SERPBASE_API_KEY")
            continue
        active.append(engine)

    # Ask every engine for page 1, then page 2, rather than exhausting one
    # provider first. With a small --max-results the old loop meant Bing never
    # contributed, so one blocked scraper could silently empty the report.
    page = 1
    while active and len(outcome.records) < settings.max_results \
            and page <= MAX_PAGES:
        still: list[str] = []
        for engine in active:
            if len(outcome.records) >= settings.max_results:
                break
            try:
                batch = await engines.fetch_engine(engine, settings, page)
            except Exception as exc:  # one provider must not sink the run
                outcome.errors.append(f"{engine}: {exc}")
                continue
            if not batch:
                continue
            for item in batch:
                if len(outcome.records) >= settings.max_results:
                    break
                if engines.is_noise_url(item.url, item.engine):
                    continue
                _add(outcome, seen, report.SearchRecord(
                    title=item.title, url=item.url, engine=item.engine,
                    snippet=item.snippet), progress)
            still.append(engine)
        active = still
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
    ordered = sorted(found.values(),
                     key=lambda profile: (
                         -_confidence(profile),
                         str(profile.get("platform") or "").casefold(),
                         str(profile.get("profile_url") or "")))
    return [profile for profile in ordered if profile]


def _confidence(profile: dict[str, object]) -> int:
    try:
        return int(profile.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0


def run_sync(settings: config.Settings,
             progress: Progress | None = None) -> report.SearchReport:
    return asyncio.run(run(settings, progress))


def write(outcome: report.SearchReport,
          settings: config.Settings) -> dict[str, str]:
    paths = report.write_all(outcome, settings.out_dir, settings.formats)
    return {name: str(path) for name, path in paths.items()}
