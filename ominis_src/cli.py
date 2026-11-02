"""Command line interface.

``ominis search "acme corp"``           one search, proxies off
``ominis username acme --format json``  profile check across platforms
``ominis proxy harvest --validate``     opt in to a fresh proxy pool
``ominis doctor``                       check the local install
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

from . import (__version__, config, engines, report, search, styxnet,
               username as username_mod)

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ERROR = 1


def _configure_stdio() -> None:
    """Make console output survive titles that are not in the local code page.

    Windows still defaults a redirected console to cp1252. A real result titled
    with an emoji then raised ``UnicodeEncodeError`` and killed the run after
    the work was already done, so the report was never written. Reconfigure
    with ``errors="replace"`` instead: an unprintable glyph becomes ``?`` and
    the search keeps going.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            # A wrapped stream (pytest, an IDE) may refuse; printing still
            # works through its own encoder.
            pass


def _engine_list(value: str) -> tuple[str, ...]:
    return config.parse_engines(value)


def _formats(value: str) -> tuple[str, ...]:
    formats = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = [name for name in formats if name not in config.OUTPUT_FORMATS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown format(s): {', '.join(unknown)}")
    return formats


def _env(name: str, fallback: str = "") -> str:
    return os.environ.get(name, fallback).strip()


def _env_flag(name: str) -> bool:
    return _env(name).lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(_env(name) or fallback)
    except ValueError:
        return fallback


def _env_float(name: str, fallback: float) -> float:
    try:
        return float(_env(name) or fallback)
    except ValueError:
        return fallback


def _env_engines() -> tuple[str, ...]:
    try:
        return config.parse_engines(_env("OMINIS_ENGINES") or None)
    except ValueError:
        return config.DEFAULT_ENGINES


def _env_formats() -> tuple[str, ...]:
    try:
        return _formats(_env("OMINIS_FORMATS") or "txt,json")
    except argparse.ArgumentTypeError:
        return ("txt", "json")


def _env_scopes() -> tuple[str, ...]:
    try:
        return _styxnet_scopes(_env("OMINIS_STYXNET_SCOPES")
                               or ",".join(styxnet.DEFAULT_SCOPES))
    except argparse.ArgumentTypeError:
        return styxnet.DEFAULT_SCOPES


def _env_proxies() -> tuple[str, ...]:
    return tuple(part.strip() for part in
                 _env("OMINIS_PROXY_POOL").split(",") if part.strip())


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def _styxnet_engines(value: str) -> int:
    number = int(value)
    if not 1 <= number <= styxnet.MAX_ENGINES:
        raise argparse.ArgumentTypeError(
            f"must be between 1 and {styxnet.MAX_ENGINES}")
    return number


def _styxnet_scopes(value: str) -> tuple[str, ...]:
    chosen = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = [scope for scope in chosen
               if scope not in styxnet.DEFAULT_SCOPES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown scope(s): {', '.join(unknown)} "
            f"(choose from {', '.join(styxnet.DEFAULT_SCOPES)})")
    return chosen or styxnet.DEFAULT_SCOPES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ominis",
        description="Discover online mentions of a query or username. "
                    "Proxies are off unless you ask for them.")
    parser.add_argument("--version", action="version",
                        version=f"Ominis OSINT {__version__}")
    sub = parser.add_subparsers(dest="command")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--proxy", action="append", default=None, metavar="URL",
                       help="proxy endpoint (repeatable); off by default")
        p.add_argument("--proxy-file", metavar="FILE",
                       help="read proxy endpoints from a file")
        p.add_argument("--timeout", type=float,
                       default=_env_float("OMINIS_TIMEOUT", 15.0),
                       help="seconds per request (default: 15)")
        p.add_argument("--no-verify", action="store_true",
                       help="skip TLS verification (not recommended)")
        p.add_argument("--format", type=_formats, default=_env_formats(),
                       help="comma-separated: txt,json,csv,md")
        p.add_argument("--out", default=_env("OMINIS_OUTPUT_DIR") or "Results",
                       metavar="DIR",
                       help="results directory (default: Results)")

    search_cmd = sub.add_parser("search", help="search the web for a query")
    search_cmd.add_argument("query", nargs="+", help="query text")
    search_cmd.add_argument("--engine", type=_engine_list,
                            default=_env_engines(),
                            help="comma-separated engines: duckduckgo,bing,serpbase")
    search_cmd.add_argument("--lang", default=_env("OMINIS_LANGUAGE"),
                            metavar="CODE", help="language code, e.g. en")
    search_cmd.add_argument("--country", default=_env("OMINIS_COUNTRY"),
                            metavar="CODE", help="country code, e.g. US")
    search_cmd.add_argument("--since", default=_env("OMINIS_SINCE"),
                            metavar="YYYY-MM-DD")
    search_cmd.add_argument("--until", default=_env("OMINIS_UNTIL"),
                            metavar="YYYY-MM-DD")
    search_cmd.add_argument("--max-results", type=_positive,
                            default=_env_int("OMINIS_MAX_RESULTS", 50))
    search_cmd.add_argument("--serpbase-key", default="",
                            help="SerpBase API key (or SERPBASE_API_KEY)")
    search_cmd.add_argument(
        "--styxnet", action=argparse.BooleanOptionalAction,
        default=_env_flag("OMINIS_STYXNET"),
        help="search through WinterGate's StyxNet engine pool instead of "
             "scraping DuckDuckGo/Bing")
    search_cmd.add_argument(
        "--styxnet-key", default="", metavar="KEY",
        help="StyxNet access key (or STYXNET_ACCESS_KEY, or "
             "~/.config/ominis/styxnet-key.txt)")
    search_cmd.add_argument(
        "--styxnet-engines", type=_styxnet_engines,
        default=_env_int("OMINIS_STYXNET_ENGINES", 35), metavar="N",
        help=f"engines per StyxNet search, 1-{styxnet.MAX_ENGINES} "
             "(default: 35)")
    search_cmd.add_argument(
        "--styxnet-scopes", type=_styxnet_scopes,
        default=_env_scopes(), metavar="LIST",
        help="comma-separated: surface,onion,deep (default: all)")
    search_cmd.add_argument("--quiet", action="store_true",
                            help="do not print each result")
    common(search_cmd)

    user_cmd = sub.add_parser("username", help="check a username across platforms")
    user_cmd.add_argument("username")
    user_cmd.add_argument("--urls", metavar="FILE",
                          help="platform URL template list")
    user_cmd.add_argument("--concurrency", type=_positive, default=8)
    user_cmd.add_argument("--all", action="store_true",
                          help="write every checked URL, not only matches")
    user_cmd.add_argument("--quiet", action="store_true")
    common(user_cmd)

    proxy_cmd = sub.add_parser("proxy", help="proxy pool tools (opt-in)")
    proxy_sub = proxy_cmd.add_subparsers(dest="proxy_action", required=True)
    harvest = proxy_sub.add_parser("harvest", help="download and validate proxies")
    harvest.add_argument("--limit", type=_positive, default=200)
    harvest.add_argument("--out", default="config/valid_proxies.txt")
    harvest.add_argument("--no-validate", action="store_true",
                         help="save candidates without checking them")

    sub.add_parser("doctor", help="check the local installation")
    return parser


def _gather_proxies(args: argparse.Namespace) -> tuple[str, ...]:
    entries = list(getattr(args, "proxy", None) or [])
    proxy_file = getattr(args, "proxy_file", None)
    if not entries and not proxy_file:
        entries.extend(_env_proxies())
    if proxy_file:
        entries.extend(config.load_proxy_file(proxy_file))
    return tuple(entries)


def _print_record(record: engines.Result) -> None:
    print(f"[{record.engine}] {record.title}")
    print(f"  {record.url}")
    if record.snippet:
        print(f"  {record.snippet[:200]}")


def cmd_search(args: argparse.Namespace) -> int:
    query = " ".join(args.query).strip()
    settings = config.Settings(
        query=query,
        engines=args.engine,
        language=args.lang,
        country=args.country,
        since=config.parse_date(args.since),
        until=config.parse_date(args.until),
        max_results=args.max_results,
        proxies=_gather_proxies(args),
        serpbase_key=args.serpbase_key or os.environ.get("SERPBASE_API_KEY", ""),
        out_dir=Path(args.out),
        formats=args.format,
        timeout=args.timeout,
        verify_tls=not args.no_verify,
        styxnet=args.styxnet,
        styxnet_key=styxnet.load_key(args.styxnet_key),
        styxnet_endpoint=(_env("OMINIS_STYXNET_ENDPOINT")
                          or styxnet.DEFAULT_ENDPOINT),
        styxnet_engines=args.styxnet_engines,
        styxnet_scopes=args.styxnet_scopes,
    )
    if settings.proxy_enabled:
        print(f"Using {len(settings.proxies)} proxy endpoint(s).")
    if settings.styxnet:
        print("Searching via StyxNet (WinterGate).")
    outcome = asyncio.run(search.run(
        settings, None if args.quiet else _print_record))
    paths = search.write(outcome, settings)
    for name, path in paths.items():
        print(f"{name}: {path}")
    for error in outcome.errors:
        print(f"warning: {error}", file=sys.stderr)
    print(f"{len(outcome.records)} result(s), "
          f"{len(outcome.profiles)} social profile(s).")
    return EXIT_OK if outcome.records or not outcome.errors else EXIT_ERROR


def cmd_username(args: argparse.Namespace) -> int:
    settings_proxies = _gather_proxies(args)
    platforms = (username_mod.load_platforms(args.urls)
                 if args.urls else None)

    def progress(hit: username_mod.Hit) -> None:
        _print_hit(hit, show_all=args.all)

    outcome = asyncio.run(username_mod.run(
        args.username, platforms, concurrency=args.concurrency,
        timeout=args.timeout, proxies=settings_proxies,
        verify_tls=not args.no_verify,
        progress=None if args.quiet else progress))
    shown = outcome.hits if args.all else outcome.found
    if shown:
        print(f"{len(outcome.found)} match(es) out of {len(outcome.hits)} checked.")
    else:
        print(f"No matches across {len(outcome.hits)} platforms.")
    paths = username_mod.write(outcome, args.out, args.format,
                               include_all=args.all)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return EXIT_OK


def _print_hit(hit: username_mod.Hit, *, show_all: bool = False) -> None:
    if hit.found:
        label = f" ({hit.platform})" if hit.platform else ""
        print(f"[found] {hit.url}{label}")
    elif hit.error:
        print(f"[error] {hit.url}: {hit.error}")
    elif show_all:
        print(f"[checked] {hit.url} - HTTP {hit.status or 'no response'}")


def cmd_proxy(args: argparse.Namespace) -> int:
    from . import proxy_handler

    if args.proxy_action != "harvest":
        return EXIT_USAGE
    valid = asyncio.run(proxy_handler.scrape_proxies(
        output=args.out, validate=not args.no_validate, limit=args.limit))
    print(f"{len(valid)} endpoint(s) saved to {args.out}")
    return EXIT_OK if valid else EXIT_ERROR


def cmd_doctor(_: argparse.Namespace) -> int:
    ok = True
    print(f"Python: {sys.version.split()[0]}")
    for module in ("httpx", "bs4", "colorama", "validators"):
        try:
            __import__(module)
            print(f"import {module}: ok")
        except Exception as exc:
            ok = False
            print(f"import {module}: FAILED ({exc})")
    import ssl

    paths = ssl.get_default_verify_paths()
    print(f"TLS CA bundle: {paths.cafile or paths.capath or 'system store'}")
    try:
        import httpx

        with httpx.Client(timeout=8.0, follow_redirects=True) as client:
            response = client.get("https://example.com/")
        print(f"HTTPS check: HTTP {response.status_code}")
    except Exception as exc:
        ok = False
        print(f"HTTPS check: FAILED ({type(exc).__name__}: {exc})")
    return EXIT_OK if ok else EXIT_ERROR


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        if sys.stdin.isatty() and sys.stdout.isatty():
            from . import wizard

            return wizard.run()
        parser.print_help()
        return EXIT_USAGE
    # Errors and warnings go to stderr; per-request HTTP chatter does not.
    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s: %(message)s")
    handlers = {
        "search": cmd_search,
        "username": cmd_username,
        "proxy": cmd_proxy,
        "doctor": cmd_doctor,
    }
    try:
        return handlers[args.command](args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
