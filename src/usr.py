"""Optional username checks for the ARG build.

Run directly with ``python -m src.usr <name>`` or add ``--username`` to the main
command. Proxies are used only if the caller supplies them.
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from pathlib import Path

import httpx

from src.tools_handler import USER_AGENTS, SearchError, _pick_proxy, _slug

PLATFORMS = Path(__file__).with_name("urls.txt")
CONCURRENCY = 8


async def check_one(username: str, template: str, *, proxies: tuple[str, ...],
                    timeout: float, verify_tls: bool) -> dict[str, object]:
    url = template.replace("{username}", username)
    if "{username}" not in template:
        if url.endswith(("/", "@", "=", "?")):
            url = url + username
        else:
            url = url.rstrip("/") + f"/{username}"
    if not url.startswith("http"):
        url = "https://" + url
    proxy = _pick_proxy(proxies)
    try:
        async with httpx.AsyncClient(proxy=proxy, timeout=timeout,
                                     verify=verify_tls,
                                     follow_redirects=True,
                                     headers={"User-Agent": random.choice(USER_AGENTS)}) as client:
            response = await client.get(url)
        return {"url": url, "status": response.status_code,
                "found": response.status_code == 200,
                "title": (response.text.split("<title>", 1)[1].split("</title>", 1)[0].strip()
                          if "<title>" in response.text else "")}
    except httpx.HTTPError as exc:
        return {"url": url, "status": 0, "found": False,
                "error": f"{type(exc).__name__}: {exc}"}


async def run(username: str, *, out_dir: Path = Path("Results"),
              proxies: tuple[str, ...] = (), timeout: float = 15.0,
              verify_tls: bool = True) -> int:
    username = username.strip()
    if not username:
        print("error: username cannot be empty", file=sys.stderr)
        return 2
    if not PLATFORMS.exists():
        print(f"error: platform list not found: {PLATFORMS}", file=sys.stderr)
        return 1
    templates = [line.strip() for line in PLATFORMS.read_text(
        encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    if not templates:
        print("error: platform list is empty", file=sys.stderr)
        return 1

    print(f"Checking {len(templates)} platforms for '{username}'...")
    queue = list(templates)
    hits: list[dict[str, object]] = []
    for start in range(0, len(queue), CONCURRENCY):
        batch = queue[start:start + CONCURRENCY]
        hits.extend(await asyncio.gather(*(
            check_one(username, template, proxies=proxies, timeout=timeout,
                      verify_tls=verify_tls) for template in batch)))
        print(f"Checked {min(start + CONCURRENCY, len(queue))}/{len(queue)}",
              end="\r")
    print()

    found = [hit for hit in hits if hit["found"]]
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"username-{_slug(username)}.txt"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"Username: {username}\nChecked: {len(hits)}\n")
        handle.write(f"Matches: {len(found)}\n")
        for hit in hits:
            if hit["found"]:
                handle.write(f"[found] {hit['url']} ({hit['status']})\n")
        errors = [hit for hit in hits if hit.get("error")]
        if errors:
            handle.write("\nErrors:\n")
            for hit in errors:
                handle.write(f"- {hit['url']}: {hit['error']}\n")
    print(f"{len(found)} match(es) out of {len(hits)}; saved to {path}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m src.usr USERNAME", file=sys.stderr)
        return 2
    try:
        return asyncio.run(run(sys.argv[1]))
    except (KeyboardInterrupt, SearchError) as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1


if __name__ == "__main__":
    raise SystemExit(main())
