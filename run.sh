#!/bin/bash
# Launch Knotee with the correct Python regardless of which venv is active.
PYTHON="/Users/madhavabhyankar/.pyenv/versions/3.13.12/bin/python3"
cd "$(dirname "$0")"
exec "$PYTHON" main.py "$@"
