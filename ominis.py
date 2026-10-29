"""Interactive entry point for the legacy 0.5.x build.

The prompts and output shape are preserved. Proxies are now a question that
defaults to "no", and the SerpBase provider is used only when a key is set.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import subprocess
import sys
import time

import urllib3
from colorama import Fore, Style, init

from ominis_src.proxy_handler import scrape_proxies, validate_proxies
from ominis_src.tools_handler import fetch_dual_engine_results

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

init(autoreset=True)

DEFAULT_NUM_RESULTS = 500
COUNTER_EMOJIS = ["*", "+", ">", "#", "~", "=", ":", "|"]
EMOJI = random.choice(COUNTER_EMOJIS)
USER_INPUTS: dict[str, str] = {}


def display_banner() -> None:
    print(
        f"""
{Fore.YELLOW}{Fore.WHITE}OMINIS-OSINT {Fore.YELLOW}- {Fore.RED}[{Fore.WHITE}Secure Web-Hunter{Fore.RED}]
{Fore.RED}~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    {Fore.YELLOW}~ {Fore.CYAN}Developer{Fore.YELLOW}: {Fore.WHITE}AnonCatalyst
    {Fore.RED}------------------------------------------
    {Fore.YELLOW}~ {Fore.CYAN}GitHub{Fore.YELLOW}: {Fore.BLUE}https://github.com/AnonCatalyst/
    {Fore.RED}------------------------------------------
    {Fore.YELLOW}~ {Fore.CYAN}Build{Fore.YELLOW}: {Fore.WHITE}0.5.0 (legacy)
    {Fore.RED}~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
{Style.RESET_ALL}"""
    )


async def get_user_input(prompt: str, options=None) -> str:
    clear_screen()
    display_banner()
    print(f"{Fore.RED}_" * 80)
    print(f"{Fore.RED}Input Statistics:{Fore.WHITE}")
    for key, value in USER_INPUTS.items():
        print(f"{Fore.YELLOW}{key}: {Fore.WHITE}{value}")
    if options:
        print(f"\n{Fore.RED}Options (examples):{Fore.WHITE}")
        for option in options:
            print(f" - {option}")
    try:
        user_input = input(
            f"\n{Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} "
            f"{prompt}: {Fore.WHITE}")
    except EOFError:
        user_input = ""
    USER_INPUTS[prompt] = user_input
    print(f"{Fore.RED}You entered: {Fore.WHITE}{user_input}\n")
    await asyncio.sleep(0.2)
    return user_input


async def _choose_proxies() -> tuple[str, ...]:
    answer = await get_user_input("Use proxies? (y/n, default n)")
    if answer.strip().lower() != "y":
        print(f"{Fore.LIGHTBLACK_EX}Running without proxies.{Style.RESET_ALL}")
        return ()
    print(f"{Fore.RED}[{Fore.GREEN}+{Fore.RED}]{Fore.WHITE} "
          f"Beginning proxy harvesting{Fore.RED}.{Style.RESET_ALL}")
    start = time.time()
    candidates = await scrape_proxies()
    if not candidates:
        print(f"{Fore.RED}No proxies harvested; continuing without them."
              f"{Style.RESET_ALL}")
        return ()
    print(f"Total proxies harvested: {Fore.GREEN}{len(candidates)}"
          f"{Style.RESET_ALL}")
    valid = await validate_proxies(candidates)
    print(f"Validated in {time.time() - start:.1f}s: "
          f"{Fore.GREEN}{len(valid)}{Style.RESET_ALL}")
    if not valid:
        print(f"{Fore.RED}No valid proxies; continuing without them."
              f"{Style.RESET_ALL}")
    return tuple(valid)


async def main() -> int:
    clear_screen()
    display_banner()
    await asyncio.sleep(0.5)

    query = (await get_user_input("Enter the query to search")).strip()
    if not query:
        logger.error("No query entered. Exiting.")
        return 2
    language = await get_user_input(
        "Enter language code (optional)",
        ["e.g., en (English)", "e.g., es (Spanish)", "e.g., fr (French)"])
    country = await get_user_input(
        "Enter country code (optional)",
        ["e.g., US (United States)", "e.g., CA (Canada)", "e.g., GB (United Kingdom)"])
    start_date = await get_user_input("Enter start date (YYYY-MM-DD, optional)")
    end_date = await get_user_input("Enter end date (YYYY-MM-DD, optional)")

    proxies = await _choose_proxies()
    if os.environ.get("SERPBASE_API_KEY"):
        print(f"{Fore.LIGHTBLACK_EX}SerpBase key found; adding the API engine."
              f"{Style.RESET_ALL}")

    print(f"{Fore.RED}_" * 80)
    try:
        await fetch_dual_engine_results(
            query,
            language=language,
            country=country,
            date_range=(start_date, end_date),
            proxies=proxies,
            max_results=DEFAULT_NUM_RESULTS,
        )
    except ValueError as exc:
        logger.error("%s", exc)
        return 2
    await asyncio.sleep(0.5)

    try:
        subprocess.run([sys.executable, "-m", "ominis_src.usr", query],
                       check=False)
    except OSError as exc:
        logger.error("username search could not start: %s", exc)
    return 0


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def run() -> int:
    try:
        return asyncio.run(main())
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(run())
