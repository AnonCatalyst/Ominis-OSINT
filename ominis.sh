#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

cd "$SCRIPT_DIR" || { echo "Failed to change directory"; exit 1; }

if [ -z "${VIRTUAL_ENV}" ]; then
    echo "Activating Virtual ENV"
    source venv/bin/activate
fi

python3 ominis.py