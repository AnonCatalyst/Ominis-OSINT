#!/bin/sh
# Local install for the legacy build. No sudo, no system-wide copy.
set -eu

cd "$(dirname "$0")"
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
printf '\nInstalled. Run: .venv/bin/python ominis.py\n'
