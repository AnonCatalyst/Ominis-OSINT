"""Guided, no-argument flow for first-time users.

Proxy harvesting is a question with a default of "no". Nothing is downloaded
or validated until the user asks for it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from colorama import Fore, Style, init

from . import config, engines, search, username as username_mod

init(autoreset=True)

BANNER = f"""
{Fore.YELLOW}Ominis-OSINT {Fore.WHITE}- Web Hunter
{Fore.RED}~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
{Fore.YELLOW}~ {Fore.CYAN}Developer{Fore.YELLOW}: {Fore.WHITE}AnonCatalyst
{Fore.YELLOW}~ {Fore.CYAN}GitHub{Fore.YELLOW}: {Fore.BLUE}https://github.com/AnonCatalyst
{Fore.YELLOW}~ {Fore.CYAN}Collective{Fore.YELLOW}: {Fore.BLUE}https://wintergate.org
"""


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{Fore.RED}[{Fore.YELLOW}?{Fore.RED}]{Fore.WHITE} "
                       f"{prompt}{suffix}: ").strip()
    except EOFError:
        return default
    return answer or default


def _yes(prompt: str, default: bool = False) -> bool:
    answer = _ask(f"{prompt} (y/n)", "y" if default else "n").lower()
    return answer.startswith("y")


def run() -> int:
    print(BANNER)
    print(f"{Fore.LIGHTBLACK_EX}Proxies are off by default. "
          f"Press Enter to accept each default.{Style.RESET_ALL}\n")
    query = _ask("Query to search")
    if not query:
        print(f"{Fore.RED}No query given.{Style.RESET_ALL}")
        return 2

    engines_text = _ask("Engines (comma separated)", "duckduckgo,bing")
    try:
        chosen = config.parse_engines(engines_text)
    except ValueError as exc:
        print(f"{Fore.RED}{exc}{Style.RESET_ALL}")
        return 2
    language = _ask("Language code (optional)")
    country = _ask("Country code (optional)")
    since = _ask("Start date YYYY-MM-DD (optional)")
    until = _ask("End date YYYY-MM-DD (optional)")
    max_results = _ask("Maximum results", "50")

    proxies: tuple[str, ...] = ()
    if _yes("Use a proxy pool", False):
        choice = _ask("Proxy file, or 'harvest' to build a pool now", "")
        if choice.lower() == "harvest":
            from . import proxy_handler

            print(f"{Fore.LIGHTBLACK_EX}Harvesting and validating proxies...")
            proxies = tuple(asyncio.run(proxy_handler.scrape_proxies()))
        elif choice:
            proxies = config.load_proxy_file(choice)

    try:
        settings = config.Settings(
            query=query, engines=chosen, language=language, country=country,
            since=config.parse_date(since), until=config.parse_date(until),
            max_results=int(max_results), proxies=proxies,
            serpbase_key=__import__("os").environ.get("SERPBASE_API_KEY", ""))
    except (ValueError, TypeError) as exc:
        print(f"{Fore.RED}{exc}{Style.RESET_ALL}")
        return 2

    print(f"\n{Fore.RED}_" * 40)
    outcome = asyncio.run(search.run(settings, _show))

    written = search.write(outcome, settings)
    for name, path in written.items():
        print(f"{Fore.GREEN}{name}{Fore.WHITE}: {path}")
    if outcome.errors:
        for error in outcome.errors:
            print(f"{Fore.YELLOW}warning:{Fore.WHITE} {error}")
    print(f"{Fore.GREEN}{len(outcome.records)} result(s), "
          f"{len(outcome.profiles)} social profile(s).{Style.RESET_ALL}")

    if _yes("Run a username search too", False):
        name = _ask("Username")
        if name:
            platforms = username_mod.load_platforms()
            result = asyncio.run(username_mod.run(
                name, platforms, proxies=proxies,
                progress=lambda hit: print(f"{Fore.GREEN}[found]{Fore.WHITE} {hit.url}")
                if hit.found else None))
            for path in username_mod.write(result, settings.out_dir,
                                           settings.formats).values():
                print(f"{Fore.GREEN}username{Fore.WHITE}: {path}")
            print(f"{len(result.found)} profile(s) found.")
    return 0


def _show(record: engines.Result) -> None:
    print(f"{Fore.YELLOW}[{record.engine}]{Fore.WHITE} {record.title}")
    print(f"  {Fore.LIGHTBLACK_EX}{record.url}{Style.RESET_ALL}")


if __name__ == "__main__":
    sys.exit(run())
