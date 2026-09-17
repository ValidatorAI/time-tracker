#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Time Tracker launcher — local development
#
#   ./run.sh                          # dev mode, auto-reload
#   ./run.sh --no-reload              # no auto-reload
#   TIME_TRACKER_PORT=9000 ./run.sh   # explicit env wins over .env
#
# Configuration precedence (same order pydantic-settings uses in app/config.py):
#
#   real environment  >  .env  >  .env.example  >  built-in defaults
#
# So a variable exported on the command line is never clobbered by the file.
# ---------------------------------------------------------------------------
set -euo pipefail

cd "$(dirname "$0")"

# --- pick an env file -------------------------------------------------------
ENV_FILE=""
if [[ -f .env ]]; then
  ENV_FILE=".env"
elif [[ -f .env.example ]]; then
  ENV_FILE=".env.example"
  echo "⚠  .env not found — using .env.example. Copy it to .env to customise."
fi

# Read KEY=VALUE pairs, skipping blanks and comments. A variable that is
# already set in the environment is left alone.
load_env_file() {
  local file="$1" raw line key value
  while IFS= read -r raw || [[ -n "$raw" ]]; do
    line="${raw%$'\r'}"                        # tolerate CRLF
    line="${line#"${line%%[![:space:]]*}"}"    # ltrim
    line="${line%"${line##*[![:space:]]}"}"    # rtrim
    [[ -z "$line" || "$line" == \#* || "$line" != *=* ]] && continue
    key="${line%%=*}"
    value="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [[ -n "${!key+x}" ]] && continue           # already set -> keep the real value
    export "$key=$value"
  done < "$file"
}

if [[ -n "$ENV_FILE" ]]; then
  load_env_file "$ENV_FILE"
fi

# --- defaults (mirror app/config.py) ---------------------------------------
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
  .venv/bin/pip install --quiet -r requirements-dev.txt
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
