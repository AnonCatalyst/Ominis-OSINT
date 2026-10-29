"""Username checks for the legacy build.

Replaces the old requests-html path with httpx, keeps the interactive prompts,
and writes one sanitised report instead of a package-local log.
"""

from __future__ import annotations

import concurrent.futures
import os
import random
import re
import sys
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from colorama import Fore, Style, init

init(autoreset=True)

USER_AGENTS = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
)
URLS_FILE = Path(__file__).with_name("urls.txt")


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-._")
    return (cleaned or "username")[:60]


def _profile_url(template: str, username: str) -> str:
    if "{username}" in template:
        return template.replace("{username}", username)
    if template.endswith(("/", "@", "=", "?")):
        return template + username
    return template.rstrip("/") + f"/{username}"


def _title(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.title.get_text(" ", strip=True) if soup.title else ""


def search_username_on_url(username: str, template: str, *,
                           include_titles: bool = True,
                           include_descriptions: bool = True,
                           timeout: float = 15.0) -> dict[str, object]:
    url = _profile_url(template, username)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True,
                          headers={"User-Agent": random.choice(USER_AGENTS)}) as client:
            response = client.get(url)
        record: dict[str, object] = {
            "url": url, "status": response.status_code,
            "found": response.status_code == 200,
        }
        if include_titles or include_descriptions:
            soup = BeautifulSoup(response.text, "html.parser")
            if include_titles:
                record["title"] = soup.title.get_text(" ", strip=True) if soup.title else ""
            if include_descriptions:
                tag = soup.find("meta", attrs={"name": "description"})
                record["description"] = tag.get("content", "") if tag else ""
        return record
    except httpx.HTTPError as exc:
        return {"url": url, "status": 0, "found": False,
                "error": f"{type(exc).__name__}: {exc}"}


def _write(username: str, hits: list[dict[str, object]]) -> Path:
    out_dir = Path("Results")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"username-{_slug(username)}_results.txt"
    found = [hit for hit in hits if hit.get("found")]
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"Username: {username}\nChecked: {len(hits)}\n")
        handle.write(f"Matches: {len(found)}\n")
        for hit in found:
            handle.write(f"[found] {hit['url']} ({hit['status']})\n")
            if hit.get("title"):
                handle.write(f"  title: {hit['title']}\n")
            if hit.get("description"):
                handle.write(f"  description: {hit['description']}\n")
        errors = [hit for hit in hits if hit.get("error")]
        if errors:
            handle.write("\nErrors:\n")
            for hit in errors:
                handle.write(f"- {hit['url']}: {hit['error']}\n")
    return path


def main(username: str) -> None:
    username = (username or "").strip()
    if not username:
        print("Error: username cannot be empty.")
        return
    if not URLS_FILE.exists():
        print(f"Error: platform list not found: {URLS_FILE}")
        return
    templates = [line.strip() for line in URLS_FILE.read_text(
        encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")]
    if not templates:
        print("Error: platform list is empty.")
        return

    print(f"{Fore.RED}_" * 80)
    include_titles = input(
        f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Include titles? "
        f"(y/n): {Style.RESET_ALL}").strip().lower() == "y"
    include_descriptions = input(
        f" {Fore.RED}[{Fore.YELLOW}!{Fore.RED}]{Fore.WHITE} Include descriptions? "
        f"(y/n): {Style.RESET_ALL}").strip().lower() == "y"
    print(f"{Fore.RED}_" * 80)

    hits: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(search_username_on_url, username, template,
                            include_titles=include_titles,
                            include_descriptions=include_descriptions): template
            for template in templates
        }
        for future in concurrent.futures.as_completed(futures):
            hit = future.result()
            hits.append(hit)
            if hit.get("found"):
                print(f"{Fore.CYAN}[found] {Fore.WHITE}{hit['url']} "
                      f"{hit['status']}{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Checked {len(hits)}/{len(templates)}",
                  end="\r")
    print()
    found = [hit for hit in hits if hit.get("found")]
    path = _write(username, hits)
    print(f"{len(found)} match(es) out of {len(hits)}; saved to {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Error: invalid number of arguments.")
        raise SystemExit(1)
    if sys.argv[1] == "--skip":
        print(f" {Fore.RED}- {Fore.LIGHTBLACK_EX}src/usr.py[ Skipping the "
              f"username search{Fore.RED}...{Style.RESET_ALL}")
        raise SystemExit(0)
    try:
        confirmation = input(
            f"\n {Fore.RED}[{Fore.YELLOW}!{Fore.RED}] {Fore.WHITE}Do you want "
            f"to run a username search{Fore.RED}? "
            f"{Fore.LIGHTBLACK_EX}({Fore.WHITE}y{Fore.LIGHTBLACK_EX}/"
            f"{Fore.WHITE}n{Fore.LIGHTBLACK_EX}){Fore.YELLOW}: "
            f"{Style.RESET_ALL}")
    except EOFError:
        confirmation = "n"
    if confirmation.strip().lower() != "y":
        raise SystemExit(0)
    main(sys.argv[1])
