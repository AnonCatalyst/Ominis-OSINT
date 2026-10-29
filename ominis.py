"""Ominis-OSINT entry point.

Run ``ominis`` with no arguments for the guided flow, or use a subcommand:

    python ominis.py search "acme corp" --format txt,json
    python ominis.py username acme
    python ominis.py doctor

The ``ominis`` console script installed by pip calls the same code.
"""

from __future__ import annotations

import sys

from ominis_src.cli import main

if __name__ == "__main__":
    sys.exit(main())
