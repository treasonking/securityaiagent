#!/usr/bin/env bash
set -euo pipefail
: "${WORKER_TOKEN:?WORKER_TOKEN must be set}"
exec .venv/bin/python -m uvicorn --factory worker.app:create_app_from_env --host "${WORKER_BIND:-10.77.0.20}" --port "${WORKER_PORT:-9000}"
