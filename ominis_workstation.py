"""Launch the Ominis Investigation Workstation.

This is a native Qt window application, not a browser page. The command line
suite remains available through ``ominis.py``; this launcher only starts the
desktop workstation.
"""

from __future__ import annotations

import sys

from ominis_workstation.app import main

if __name__ == "__main__":
    raise SystemExit(main())
