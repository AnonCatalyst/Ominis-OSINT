"""Run one search across the selected providers and write the report."""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Callable

from . import config, engines, pagescan, platforms, report, styxnet, utils

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

    if settings.scan_pages and outcome.records:
        await _scan_pass(settings, outcome)

    outcome.mentions = _mentions(outcome, settings.query)
    outcome.profiles = _profiles(outcome.profiles, outcome.records)
    return outcome


async def _scan_pass(settings: config.Settings,
                     outcome: report.SearchReport) -> None:
    """Read the result pages themselves and keep the evidence on each row."""
    tally = await pagescan.scan_records(
        outcome.records, settings.query, limit=settings.scan_limit,
        concurrency=min(8, max(2, settings.scan_limit)),
        timeout=settings.timeout, proxies=settings.proxies,
        verify_tls=settings.verify_tls,
        use_env_proxy=settings.use_env_proxy,
    )
    if tally["errors"]:
        outcome.errors.append(
            f"page scan: {tally['errors']} of {tally['scanned']} result pages "
            "could not be read")


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
        if not existing.platform and record.platform:
            existing.platform = record.platform
            existing.category = record.category
            existing.confidence = record.confidence
            existing.handle = record.handle
        return False
    record.position = len(outcome.records) + 1
    if not record.platform:
        # Record the profile shape now, so an unscanned result still reports
        # the platform, category, confidence and handle the URL rules read.
        detected = platforms.detect_profiles(record.url)
        if detected:
            record.platform = str(detected[0].get("platform") or "")
            record.category = str(detected[0].get("category") or "")
            record.confidence = int(detected[0].get("confidence") or 0)
            record.handle = str(detected[0].get("handle") or "")
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
            use_env_proxy=settings.use_env_proxy,
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
        evidence = _evidence(record)
        for profile in utils.find_social_profiles(record.url):
            candidate = _with_evidence(profile, record, evidence)
            key = platforms.profile_key(candidate)
            if key:
                found.setdefault(key, candidate)
        # A redirect can land on a profile that the original URL did not look
        # like (short links, regional hosts). The page scan knows the final URL.
        if record.platform and (record.matched or not record.scanned):
            candidate = {
                "platform": record.platform,
                "profile_url": record.final_url or record.url,
                "category": record.category,
                "confidence": record.confidence or evidence["confidence"],
                "handle": record.handle,
                "source": record.signal or "url",
                "title": record.page_title or record.title,
                "description": record.page_description,
                "status": record.status,
                "verified": bool(record.matched),
            }
            key = platforms.profile_key(candidate)
            if key:
                existing = found.get(key)
                if existing is None:
                    found[key] = candidate
                elif record.matched:
                    for field, value in candidate.items():
                        if value not in ("", None, 0, False):
                            existing.setdefault(field, value)
    ordered = sorted(found.values(),
                     key=lambda profile: (
                         -_confidence(profile),
                         str(profile.get("platform") or "").casefold(),
                         str(profile.get("profile_url") or "")))
    return [profile for profile in ordered if profile]


def _evidence(record: report.SearchRecord) -> dict[str, object]:
    """Turn one page scan into the fields a profile row can carry."""
    signal = str(record.signal or "")
    if signal in {"redirect", "canonical", "structured", "metadata"}:
        confidence = 92
    elif signal == "body":
        confidence = 82
    elif signal == "url":
        confidence = 60
    else:
        confidence = 45
    return {"signal": signal, "confidence": confidence,
            "verified": bool(record.matched)}


def _with_evidence(profile: dict[str, object],
                   record: report.SearchRecord,
                   evidence: dict[str, object]) -> dict[str, object]:
    candidate = dict(profile)
    if record.scanned:
        candidate["page_signal"] = record.signal
        candidate["verified"] = bool(record.matched)
        if record.signal == "url":
            # The URL table recognised a profile shape, but the page did not
            # confirm it. Keep the lead and say so; never promote it.
            candidate["confidence"] = min(
                _confidence(candidate), 75)
        elif record.matched:
            candidate["confidence"] = max(
                _confidence(candidate), int(evidence["confidence"]))
            candidate["source"] = record.signal
        elif record.error:
            candidate["confidence"] = min(_confidence(candidate), 55)
    if record.page_title:
        candidate["title"] = record.page_title
    if record.page_description:
        candidate["description"] = record.page_description
    if record.handle and (record.matched or not record.scanned):
        candidate["handle"] = record.handle
    if record.status:
        candidate["status"] = record.status
    # Only a confirmed page may move a profile URL. An unconfirmed check that
    # redirected to a login or home page must keep the URL that was tested.
    if record.final_url and record.matched:
        candidate["profile_url"] = record.final_url
    return candidate


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
