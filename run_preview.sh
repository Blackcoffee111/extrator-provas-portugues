#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHONPATH="$SCRIPT_DIR/src" exec /opt/homebrew/bin/python3 -m exames_pipeline "$@"
