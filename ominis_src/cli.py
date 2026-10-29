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

from . import __version__, config, engines, report, search, username as username_mod

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ERROR = 1


def _engine_list(value: str) -> tuple[str, ...]:
    return config.parse_engines(value)


def _formats(value: str) -> tuple[str, ...]:
    formats = tuple(part.strip() for part in value.split(",") if part.strip())
    unknown = [name for name in formats if name not in config.OUTPUT_FORMATS]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"unknown format(s): {', '.join(unknown)}")
    return formats


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ominis",
        description="Discover online mentions of a query or username. "
                    "Proxies are off unless you ask for them.")
    parser.add_argument("--version", action="version",
                        version=f"Ominis OSINT {__version__}")
    sub = parser.add_subparsers(dest="command")

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--proxy", action="append", default=[], metavar="URL",
                       help="proxy endpoint (repeatable); off by default")
        p.add_argument("--proxy-file", metavar="FILE",
                       help="read proxy endpoints from a file")
        p.add_argument("--timeout", type=float, default=15.0,
                       help="seconds per request (default: 15)")
        p.add_argument("--no-verify", action="store_true",
                       help="skip TLS verification (not recommended)")
        p.add_argument("--format", type=_formats, default=("txt", "json"),
                       help="comma-separated: txt,json,csv,md")
        p.add_argument("--out", default="Results", metavar="DIR",
                       help="results directory (default: Results)")

    search_cmd = sub.add_parser("search", help="search the web for a query")
    search_cmd.add_argument("query", nargs="+", help="query text")
    search_cmd.add_argument("--engine", type=_engine_list,
                            default=config.DEFAULT_ENGINES,
                            help="comma-separated engines: duckduckgo,bing,serpbase")
    search_cmd.add_argument("--lang", default="", metavar="CODE",
                            help="language code, e.g. en")
    search_cmd.add_argument("--country", default="", metavar="CODE",
                            help="country code, e.g. US")
    search_cmd.add_argument("--since", default="", metavar="YYYY-MM-DD")
    search_cmd.add_argument("--until", default="", metavar="YYYY-MM-DD")
    search_cmd.add_argument("--max-results", type=_positive, default=50)
    search_cmd.add_argument("--serpbase-key", default="",
                            help="SerpBase API key (or SERPBASE_API_KEY)")
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
    entries = list(getattr(args, "proxy", []) or [])
    if getattr(args, "proxy_file", None):
        entries.extend(config.load_proxy_file(args.proxy_file))
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
    )
    if settings.proxy_enabled:
        print(f"Using {len(settings.proxies)} proxy endpoint(s).")
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
    outcome = asyncio.run(username_mod.run(
        args.username, platforms, concurrency=args.concurrency,
        timeout=args.timeout, proxies=settings_proxies,
        verify_tls=not args.no_verify,
        progress=None if args.quiet else _print_hit))
    shown = outcome.hits if args.all else outcome.found
    if shown:
        print(f"{len(outcome.found)} match(es) out of {len(outcome.hits)} checked.")
    else:
        print(f"No matches across {len(outcome.hits)} platforms.")
    paths = username_mod.write(outcome, args.out, args.format)
    for name, path in paths.items():
        print(f"{name}: {path}")
    return EXIT_OK


def _print_hit(hit: username_mod.Hit) -> None:
    if hit.found:
        print(f"[found] {hit.url}")
    elif hit.error:
        print(f"[error] {hit.url}: {hit.error}")


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
