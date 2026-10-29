"""Ominis-OSINT ARG build.

The original 10.12.2024 arguments release kept its command-line shape. This
build keeps the same flags, fixes the broken transport, makes proxies opt-in and
adds an optional SerpBase Google leg.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import sys
from pathlib import Path

import urllib3
from colorama import Fore, Style, init

from src import tools_handler
from src.proxy_handler import scrape_proxies, validate_proxies

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
init(autoreset=True)

VERSION = "10.12.2024-fixed"
DEFAULT_MAX_RESULTS = 100
COUNTER_EMOJIS = ["*", "+", ">", "#", "~", "=", ":", "|"]


def display_banner() -> None:
    print(
        f"""
{Fore.YELLOW}{Fore.WHITE}OMINIS-OSINT {Fore.YELLOW}- {Fore.RED}[{Fore.WHITE}Secure Web-Hunter{Fore.RED}]
{Fore.RED}~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    {Fore.YELLOW}~ {Fore.CYAN}Developer{Fore.YELLOW}: {Fore.WHITE}AnonCatalyst
    {Fore.RED}------------------------------------------
    {Fore.YELLOW}~ {Fore.CYAN}GitHub{Fore.YELLOW}: {Fore.BLUE}https://github.com/AnonCatalyst/
    {Fore.RED}------------------------------------------
    {Fore.YELLOW}~ {Fore.CYAN}Build{Fore.YELLOW}: {Fore.WHITE}ARG {VERSION}
    {Fore.RED}~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    {Fore.YELLOW}~ {Fore.CYAN}Proxies{Fore.YELLOW}: {Fore.WHITE}off unless you pass --proxy
{Style.RESET_ALL}"""
    )


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ominis.py",
        description="Secure Web-Hunter - ARG build. Proxies are optional.",
    )
    parser.add_argument("-q", "--query", required=True,
                        help="the query to search")
    parser.add_argument("-l", "--language", default="",
                        help="language code, e.g. en or lang_en")
    parser.add_argument("-c", "--country", default="",
                        help="country code, e.g. US or countryUS")
    parser.add_argument("-s", "--start_date", default="",
                        help="start date (YYYY-MM-DD or MM/DD/YYYY)")
    parser.add_argument("-e", "--end_date", default="",
                        help="end date (YYYY-MM-DD or MM/DD/YYYY)")
    parser.add_argument("-p", "--proxy", action="append", default=[],
                        metavar="URL", help="proxy endpoint (repeatable)")
    parser.add_argument("--proxy-file", metavar="FILE",
                        help="read proxy endpoints from a file")
    parser.add_argument("--scrape-proxies", action="store_true",
                        help="harvest and validate a proxy pool before searching")
    parser.add_argument("--engine", default="google",
                        help="comma-separated: google,duckduckgo,bing,serpbase")
    parser.add_argument("--serpbase-key", default="",
                        help="SerpBase API key (or SERPBASE_API_KEY)")
    parser.add_argument("--max-results", type=int, default=DEFAULT_MAX_RESULTS,
                        help=f"results to keep (default: {DEFAULT_MAX_RESULTS})")
    parser.add_argument("--out", default="Results", metavar="DIR",
                        help="output directory (default: Results)")
    parser.add_argument("--username", default="",
                        help="also run a username search for this handle")
    parser.add_argument("--no-verify", action="store_true",
                        help="skip TLS verification (not recommended)")
    parser.add_argument("--no-banner", action="store_true")
    parser.add_argument("--version", action="version",
                        version=f"Ominis-OSINT ARG {VERSION}")
    return parser.parse_args(argv)


def _engines(value: str) -> tuple[str, ...]:
    known = ("google", "duckduckgo", "bing", "serpbase")
    engines = tuple(part.strip().lower() for part in value.split(",")
                    if part.strip())
    unknown = [name for name in engines if name not in known]
    if unknown:
        raise ValueError(f"unknown engine(s): {', '.join(unknown)}")
    return engines or ("google",)


def _proxies(args: argparse.Namespace) -> tuple[str, ...]:
    entries = list(args.proxy or [])
    if args.proxy_file:
        path = Path(args.proxy_file)
        if not path.exists():
            raise ValueError(f"proxy file not found: {path}")
        entries.extend(line.strip() for line in path.read_text(
            encoding="utf-8").splitlines() if line.strip())
    return tuple(entries)


async def _maybe_harvest(args: argparse.Namespace) -> tuple[str, ...]:
    proxies = _proxies(args)
    if proxies or not args.scrape_proxies:
        return proxies
    print(f"{Fore.RED}[{Fore.GREEN}+{Fore.RED}]{Fore.WHITE} Harvesting proxies "
          f"(opt-in){Fore.RED}.{Style.RESET_ALL}")
    candidates = await scrape_proxies()
    if not candidates:
        print(f"{Fore.RED}No proxies harvested; continuing without them."
              f"{Style.RESET_ALL}")
        return ()
    valid = await validate_proxies(candidates)
    print(f"{Fore.GREEN}{len(valid)} valid proxy endpoint(s).{Style.RESET_ALL}")
    return tuple(valid)


async def run(argv: list[str] | None = None) -> int:
    args = parse_arguments(argv)
    if not args.no_banner:
        os.system("cls" if os.name == "nt" else "clear")
        display_banner()

    query = (args.query or "").strip()
    if not query:
        print("error: query cannot be empty", file=sys.stderr)
        return 2

    engines = _engines(args.engine)
    key = args.serpbase_key or os.environ.get("SERPBASE_API_KEY", "")
    if "serpbase" in engines and not key:
        print("warning: serpbase selected without SERPBASE_API_KEY; "
              "falling back to google", file=sys.stderr)
        engines = tuple(name for name in engines if name != "serpbase") or ("google",)
    if key and "google" in engines and "serpbase" not in engines:
        # The whole point of the optional API: take over the Google leg.
        engines = tuple("serpbase" if name == "google" else name
                        for name in engines)

    proxies = await _maybe_harvest(args)
    if proxies:
        print(f"Using {len(proxies)} proxy endpoint(s).")
    else:
        print("Running without proxies.")

    result = await tools_handler.fetch_results(
        query,
        engines=engines,
        language=args.language,
        country=args.country,
        date_range=(args.start_date, args.end_date),
        proxies=proxies,
        max_results=max(1, args.max_results),
        out_dir=Path(args.out),
        serpbase_key=key,
        verify_tls=not args.no_verify,
    )
    print(f"\n{Fore.GREEN}Search completed.{Style.RESET_ALL} "
          f"{len(result['records'])} result(s).")
    for name, path in result["paths"].items():
        print(f"{name}: {path}")

    if args.username:
        code = await _username_search(args)
        return code
    return 0 if result["records"] or not result["errors"] else 1


async def _username_search(args: argparse.Namespace) -> int:
    from src import usr

    return await usr.run(
        args.username,
        out_dir=Path(args.out),
        proxies=tuple(args.proxy or ()),
        verify_tls=not args.no_verify,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run(argv))
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
