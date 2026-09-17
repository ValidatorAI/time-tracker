#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Time Tracker launcher
#
# Loads environment variables from ./.env (falling back to ./.env.example),
# then starts the FastAPI app with uvicorn.
#
#   ./run.sh              # dev mode (reload)
#   ./run.sh --no-reload  # production-ish
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")"

# --- pick an env file -------------------------------------------------------
if [[ -f .env ]]; then
  ENV_FILE=".env"
elif [[ -f .env.example ]]; then
  ENV_FILE=".env.example"
  echo "⚠  .env not found — using .env.example. Copy it to .env to customise."
else
  echo "✖ Neither .env nor .env.example exists." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# --- sane defaults (mirror app/config.py) -----------------------------------
: "${TIME_TRACKER_HOST:=127.0.0.1}"
: "${TIME_TRACKER_PORT:=8787}"
: "${TIME_TRACKER_ENV:=dev}"
: "${TIME_TRACKER_LOG_LEVEL:=info}"
: "${TIME_TRACKER_DB_PATH:=./data/time_tracker.db}"
export TIME_TRACKER_HOST TIME_TRACKER_PORT TIME_TRACKER_ENV \
       TIME_TRACKER_LOG_LEVEL TIME_TRACKER_DB_PATH

# --- venv -------------------------------------------------------------------
if [[ ! -x .venv/bin/python ]]; then
  echo "Creating virtualenv…"
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

RELOAD="--reload"
[[ "${1:-}" == "--no-reload" ]] && RELOAD=""

echo "──────────────────────────────────────────────"
echo " Time Tracker"
echo "   env      : $TIME_TRACKER_ENV"
echo "   database : $TIME_TRACKER_DB_PATH"
echo "   timezone : ${TIME_TRACKER_TIMEZONE:-<auto-detect>}"
echo "   URL      : http://$TIME_TRACKER_HOST:$TIME_TRACKER_PORT/"
echo "   API docs : http://$TIME_TRACKER_HOST:$TIME_TRACKER_PORT/docs"
echo "──────────────────────────────────────────────"

exec .venv/bin/python -m uvicorn app.main:app \
  --host "$TIME_TRACKER_HOST" \
  --port "$TIME_TRACKER_PORT" \
  --log-level "$TIME_TRACKER_LOG_LEVEL" \
  $RELOAD
