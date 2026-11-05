"""Build the JSON payloads the workstation screenshots are rendered from.

Two sources are supported:

* ``--live`` runs the workstation backend now (network access required).
* ``--from-captures`` converts the verified CLI captures in ``docs/captures``
  into the same payload shape. It is deterministic and needs no network, so a
  screenshot can always be rebuilt.

Run from the repository root.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ominis_src import __version__  # noqa: E402
from ominis_workstation import backend  # noqa: E402


def _write(name: str, payload: dict[str, Any], out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                    encoding="utf-8")
    print(path)
    return path


def from_captures(out: Path) -> None:
    search = json.loads((ROOT / "docs" / "captures" / "raw" / "local-search" /
                         "AnonCatalyst.json").read_text(encoding="utf-8"))
    _write("local-search", {
        "mode": backend.MODE_SEARCH,
        "target": search["summary"]["query"],
        "started": search["summary"]["started"],
        "elapsed_ms": 4569,
        "summary": search["summary"],
        "results": search["results"],
        "profiles": search["profiles"],
        "errors": search["summary"].get("errors") or [],
        "paths": {"txt": "AnonCatalyst.txt", "json": "AnonCatalyst.json",
                  "md": "AnonCatalyst.md"},
        "version": __version__,
    }, out)

    user = json.loads((ROOT / "docs" / "captures" / "raw" / "username" /
                       "username-AnonCatalyst.json").read_text(encoding="utf-8"))
    profiles = [{
        "platform": hit.get("platform") or "",
        "profile_url": hit.get("url") or "",
        "category": hit.get("category") or "",
        "confidence": hit.get("confidence") or 0,
        "title": hit.get("title") or "",
        "source": hit.get("match") or "local",
        "status": hit.get("status") or 0,
    } for hit in user.get("profiles", [])]
    _write("username", {
        "mode": backend.MODE_USERNAME,
        "target": user["username"],
        "started": user["started"],
        "elapsed_ms": 55995,
        "summary": {
            "checked": user["checked"],
            "found": user["found"],
            "errors": len(user.get("errors") or []),
            "elapsed_ms": 55995,
        },
        "hits": user.get("hits") or user.get("profiles") or [],
        "profiles": profiles,
        "errors": [{"url": hit.get("url"), "error": hit.get("error")}
                   for hit in user.get("errors") or []],
        "paths": {"txt": "username-AnonCatalyst.txt",
                  "json": "username-AnonCatalyst.json",
                  "md": "username-AnonCatalyst.md",
                  "csv": "username-AnonCatalyst.csv"},
        "version": __version__,
    }, out)

    styx = json.loads((ROOT / "docs" / "captures" / "raw" / "styxnet" /
                       "AnonCatalyst.json").read_text(encoding="utf-8"))
    _write("styxnet", {
        "mode": backend.MODE_STYXNET,
        "target": styx["summary"]["query"],
        "started": styx["summary"]["started"],
        "elapsed_ms": int((styx["summary"].get("styxnet_meta") or {})
                          .get("elapsed_ms") or 11457),
        "summary": styx["summary"],
        "results": styx["results"],
        "profiles": styx["profiles"],
        "errors": styx["summary"].get("errors") or [],
        "paths": {"txt": "AnonCatalyst.txt", "json": "AnonCatalyst.json",
                  "md": "AnonCatalyst.md"},
        "version": __version__,
    }, out)


def live(out: Path) -> None:
    runs = (
        ("local-search", backend.MODE_SEARCH, "AnonCatalyst", 20),
        ("username", backend.MODE_USERNAME, "AnonCatalyst", 0),
        ("styxnet", backend.MODE_STYXNET, "AnonCatalyst", 15),
    )
    for name, mode, target, limit in runs:
        request = backend.InvestigationRequest(
            mode=mode, target=target,
            max_results=limit or 25,
            include_all=mode == backend.MODE_USERNAME,
            out_dir=out / "results",
            formats=("txt", "json", "md", "csv"),
        )
        payload = backend.execute(request, log=lambda line: print("  " + line))
        _write(name, payload, out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true",
                        help="run the backend now instead of replaying captures")
    parser.add_argument("--out", default=str(ROOT / "docs" / "workstation" /
                                             "captures"))
    args = parser.parse_args()
    out = Path(args.out)
    if args.live:
        live(out)
    else:
        from_captures(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
