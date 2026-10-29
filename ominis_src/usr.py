"""Compatibility shim for the old username search.

``python -m ominis_src.usr NAME`` used to be the only entry point. It still
works, but it now uses the shared HTTPX client and writes the same files as
``ominis username``.
"""

from __future__ import annotations

import sys

from colorama import Fore, init

from . import username as _username

init(autoreset=True)


def main(username: str, *, quiet: bool = False):
    platforms = _username.load_platforms()
    print(f"{Fore.LIGHTBLACK_EX}Checking {len(platforms)} platforms...")
    result = _username.run_sync(
        username, platforms,
        progress=None if quiet else _report)
    print(f"{Fore.GREEN}{len(result.found)} profile(s) found "
          f"out of {len(result.hits)} checked.{Fore.RESET}")
    for path in _username.write(result, "Results", ("txt", "json")).values():
        print(path)
    return result


def _report(hit: _username.Hit) -> None:
    if hit.found:
        print(f"{Fore.GREEN}[found]{Fore.WHITE} {hit.url}")
    elif hit.error:
        print(f"{Fore.RED}[error]{Fore.WHITE} {hit.url}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] in {"-h", "--help"}:
        print("usage: python -m ominis_src.usr USERNAME")
        raise SystemExit(2)
    main(sys.argv[1])
