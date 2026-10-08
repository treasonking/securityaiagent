#!/usr/bin/env bash
set -euo pipefail
exec .venv/bin/python -m uvicorn target.app:app --host "${TARGET_BIND:-10.78.0.30}" --port "${TARGET_PORT:-8080}"
