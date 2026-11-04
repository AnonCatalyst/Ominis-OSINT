"""Backend bridge between the Qt window and the Ominis engine.

The window never talks to the network itself. Every run goes through
``ominis_src`` on a worker thread with its own event loop, so the interface
stays responsive and a run can be cancelled.
"""

from __future__ import annotations

import asyncio
import os
import stat
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from ominis_src import __version__, config, report, search, styxnet
from ominis_src import username as username_mod

MODE_SEARCH = "Web search"
MODE_USERNAME = "Username"
MODE_STYXNET = "StyxNet"
MODES = (MODE_SEARCH, MODE_USERNAME, MODE_STYXNET)

ENGINES = ("duckduckgo", "bing", "serpbase")
SCOPES = ("surface", "onion", "deep")


@dataclass
class InvestigationRequest:
    mode: str = MODE_SEARCH
    target: str = ""
    engines: tuple[str, ...] = ("duckduckgo", "bing")
    max_results: int = 25
    language: str = ""
    country: str = ""
    since: str = ""
    until: str = ""
    out_dir: Path = field(default_factory=lambda: Path("Results"))
    formats: tuple[str, ...] = ("txt", "json", "md")
    concurrency: int = 8
    timeout: float = 15.0
    include_all: bool = False
    styxnet_engines: int = 35
    styxnet_scopes: tuple[str, ...] = SCOPES
    styxnet_key: str = ""

    @property
    def is_username(self) -> bool:
        return self.mode == MODE_USERNAME

    @property
    def is_styxnet(self) -> bool:
        return self.mode == MODE_STYXNET


def _elapsed(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def search_payload(outcome: report.SearchReport, paths: dict[str, str],
                   elapsed_ms: int) -> dict[str, Any]:
    return {
        "mode": MODE_STYXNET if outcome.styxnet else MODE_SEARCH,
        "target": outcome.query,
        "started": outcome.started,
        "elapsed_ms": elapsed_ms,
        "summary": outcome.summary(),
        "results": [asdict(record) for record in outcome.records],
        "profiles": outcome.profiles,
        "errors": list(outcome.errors),
        "paths": paths,
        "version": __version__,
    }


def username_payload(outcome: username_mod.UsernameReport,
                     paths: dict[str, str], elapsed_ms: int) -> dict[str, Any]:
    found = outcome.found
    errors = outcome.errors
    return {
        "mode": MODE_USERNAME,
        "target": outcome.username,
        "started": outcome.started,
        "elapsed_ms": elapsed_ms,
        "summary": {
            "checked": len(outcome.hits),
            "found": len(found),
            "errors": len(errors),
            "elapsed_ms": elapsed_ms,
        },
        "hits": [asdict(hit) for hit in outcome.hits],
        "profiles": [
            {
                "platform": hit.platform,
                "profile_url": hit.url,
                "category": hit.category,
                "confidence": hit.confidence,
                "title": hit.title,
                "source": hit.match or "local",
                "status": hit.status,
            }
            for hit in found
        ],
        "errors": [
            {"url": hit.url, "error": hit.error} for hit in errors
        ],
        "paths": paths,
        "version": __version__,
    }


def build_settings(request: InvestigationRequest) -> config.Settings:
    styx = request.is_styxnet
    key = styxnet.load_key(request.styxnet_key) if styx else ""
    return config.Settings(
        query=request.target,
        engines=request.engines or config.DEFAULT_ENGINES,
        language=request.language,
        country=request.country,
        since=request.since,
        until=request.until,
        max_results=request.max_results,
        out_dir=Path(request.out_dir),
        formats=tuple(request.formats) or ("txt", "json"),
        timeout=request.timeout,
        styxnet=styx,
        styxnet_key=key,
        styxnet_engines=request.styxnet_engines,
        styxnet_scopes=tuple(request.styxnet_scopes) or SCOPES,
    )


async def execute_async(request: InvestigationRequest,
                        log: Callable[[str], None],
                        progress: Callable[[int, int], None]) -> dict[str, Any]:
    target = str(request.target or "").strip()
    if not target:
        raise ValueError("Enter a target first.")
    started = time.perf_counter()

    if request.is_username:
        total = len(username_mod.load_platforms())
        done = 0

        def on_hit(hit: username_mod.Hit) -> None:
            nonlocal done
            done += 1
            if hit.found:
                label = f" ({hit.platform})" if hit.platform else ""
                log(f"match  {hit.url}{label}  [{hit.match or 'signal'}]")
            elif hit.error:
                log(f"error  {hit.url}  {hit.error}")
            progress(done, total)

        log(f"Checking {total} platform templates for {target} ...")
        outcome = await username_mod.run(
            target, concurrency=request.concurrency,
            timeout=request.timeout, progress=on_hit)
        paths = username_mod.write(
            outcome, request.out_dir, request.formats,
            include_all=request.include_all)
        payload = username_payload(outcome, paths, _elapsed(started))
        log(f"Done: {payload['summary']['found']} matches out of "
            f"{payload['summary']['checked']} checked.")
        return payload

    settings = build_settings(request)
    if settings.styxnet:
        log(f"Searching via StyxNet for {target} ...")
    else:
        log(f"Searching {', '.join(settings.engines)} for {target} ...")
    seen = 0

    def on_result(result: Any) -> None:
        nonlocal seen
        seen += 1
        log(f"[{result.engine}] {result.title or result.url}")
        progress(seen, settings.max_results)

    outcome = await search.run(settings, progress=on_result)
    paths = search.write(outcome, settings)
    payload = search_payload(outcome, paths, _elapsed(started))
    for message in outcome.errors:
        log(f"warning  {message}")
    if settings.styxnet and not outcome.records and not outcome.profiles:
        log("StyxNet returned nothing. Check the archive id in the summary.")
    log(f"Done: {payload['summary']['results']} results, "
        f"{payload['summary']['profiles']} profiles.")
    return payload


def execute(request: InvestigationRequest,
            log: Callable[[str], None] = lambda _: None,
            progress: Callable[[int, int], None] = lambda *_: None) -> dict[str, Any]:
    return asyncio.run(execute_async(request, log, progress))


def friendly_error(exc: BaseException) -> str:
    text = str(exc).strip()
    if isinstance(exc, ValueError):
        return text or "The request was rejected."
    if isinstance(exc, styxnet.StyxNetError):
        return text
    if isinstance(exc, OSError):
        return f"Cannot write files: {text or exc}"
    return f"{type(exc).__name__}: {text or 'unexpected failure'}"


class InvestigationWorker(QThread):
    """Runs one investigation and reports back on the Qt signal bus."""

    log = Signal(str)
    progress = Signal(int, int)
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, request: InvestigationRequest,
                 parent: object | None = None) -> None:
        super().__init__(parent)  # type: ignore[arg-type]
        self.request = request
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task | None = None
        self._cancelled = False

    def run(self) -> None:  # noqa: D102 - QThread entry point
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            asyncio.set_event_loop(loop)
            self._task = loop.create_task(
                execute_async(self.request, self.log.emit, self.progress.emit))
            if self._cancelled:
                self._task.cancel()
            payload = loop.run_until_complete(self._task)
        except asyncio.CancelledError:
            self.failed.emit("Stopped by operator.")
        except BaseException as exc:  # the thread must never die silently
            self.failed.emit(friendly_error(exc))
        else:
            if not self._cancelled:
                self.finished.emit(payload)
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception:
                pass
            loop.close()
            self._loop = None
            self._task = None

    def cancel(self) -> None:
        self._cancelled = True
        loop, task = self._loop, self._task
        if loop is not None and task is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass


class DoctorWorker(QThread):
    finished = Signal(list)

    def run(self) -> None:
        self.finished.emit(doctor_checks())


def doctor_checks() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append({"label": "Ominis", "ok": True,
                   "detail": f"version {__version__}"})
    checks.append({"label": "Python", "ok": True,
                   "detail": sys.version.split()[0]})
    for module in ("httpx", "bs4", "colorama", "validators"):
        try:
            __import__(module)
        except Exception as exc:
            checks.append({"label": f"import {module}", "ok": False,
                           "detail": str(exc)})
        else:
            checks.append({"label": f"import {module}", "ok": True,
                           "detail": "ok"})
    try:
        import ssl

        paths = ssl.get_default_verify_paths()
        checks.append({"label": "TLS CA bundle", "ok": True,
                       "detail": paths.cafile or paths.capath or "system store"})
    except Exception as exc:
        checks.append({"label": "TLS CA bundle", "ok": False,
                       "detail": str(exc)})
    # Never echo proxy values: they can embed credentials.
    proxy_names = sorted({
        name for name in os.environ
        if name.upper() in {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"}
        and os.environ.get(name, "").strip()
    })
    checks.append({
        "label": "Proxy environment",
        "ok": True,
        "detail": ("not set, direct connections"
                   if not proxy_names
                   else "set for " + ", ".join(proxy_names) + " (values hidden)"),
    })
    try:
        import httpx

        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            response = client.get("https://example.com/")
        detail = f"HTTP {response.status_code}"
        if proxy_names:
            detail += "; environment proxy in use"
        checks.append({"label": "HTTPS check",
                       "ok": response.status_code < 400,
                       "detail": detail})
    except Exception as exc:
        detail = f"{type(exc).__name__}: {str(exc)[:140]}"
        if proxy_names:
            detail += " (environment proxy is set)"
        checks.append({"label": "HTTPS check", "ok": False, "detail": detail})
    key = styxnet.load_key()
    checks.append({
        "label": "StyxNet key",
        "ok": bool(key),
        "detail": f"saved, {len(key)} characters" if key else "not saved",
    })
    return checks


def key_file() -> Path:
    candidates = styxnet.key_candidates()
    return candidates[0]


def key_status() -> str:
    key = styxnet.load_key()
    if not key:
        return "No key saved"
    return f"Key saved ({len(key)} characters)"


def save_key(value: str) -> Path:
    key = str(value or "").strip()
    if not key.startswith("sgn_") or len(key) < 20:
        raise ValueError("That does not look like a StyxNet key (expected sgn_...).")
    path = key_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(key, encoding="utf-8")
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    _restrict_windows_acl(path)
    return path


def clear_key() -> bool:
    removed = False
    for path in styxnet.key_candidates():
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            continue
        removed = True
    return removed


def _restrict_windows_acl(path: Path) -> None:
    """Best effort: keep the key file readable only by the current account."""
    if sys.platform != "win32":
        return
    import subprocess

    user = os.environ.get("USERNAME", "")
    if not user:
        return
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r",
             "/grant:r", f"{user}:F"],
            check=False, capture_output=True, timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        pass
