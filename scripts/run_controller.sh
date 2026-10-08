#!/usr/bin/env bash
set -euo pipefail
: "${WORKER_TOKEN:?WORKER_TOKEN must be set}"
: "${APP_SESSION_SECRET:?APP_SESSION_SECRET must be set}"
exec .venv/bin/python -m uvicorn --factory controller.api:create_app_from_env --host "${APP_BIND:-192.168.56.10}" --port "${APP_PORT:-8000}" --workers 1
