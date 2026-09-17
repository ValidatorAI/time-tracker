#!/usr/bin/env sh
# ---------------------------------------------------------------------------
# Container entrypoint.
#
# Every knob is an environment variable (TIME_TRACKER_*), so the image stays
# configuration-free. With no arguments it starts uvicorn; pass a command to
# override, e.g. `docker run --rm -it time-tracker sh`.
# ---------------------------------------------------------------------------
set -eu

HOST="${TIME_TRACKER_HOST:-0.0.0.0}"
PORT="${TIME_TRACKER_PORT:-8787}"
LOG_LEVEL="${TIME_TRACKER_LOG_LEVEL:-info}"
DB_PATH="${TIME_TRACKER_DB_PATH:-/data/time_tracker.db}"

# Let the caller run an arbitrary command instead of the server.
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Make sure the parent directory of the database exists. SQLite creates the
# file itself, not the tree above it.
DB_DIR="$(dirname "$DB_PATH")"
if [ ! -d "$DB_DIR" ]; then
    mkdir -p "$DB_DIR" 2>/dev/null || {
        echo "✖ cannot create database directory $DB_DIR" >&2
        echo "  if you bind-mounted it, make it writable by uid 10001" >&2
        exit 1
    }
fi

if [ ! -w "$DB_DIR" ]; then
    echo "✖ database directory $DB_DIR is not writable by uid $(id -u)" >&2
    echo "  use the named volume, or: docker run -u \$(id -u):\$(id -g) ..." >&2
    exit 1
fi

echo "──────────────────────────────────────────────"
echo " Time Tracker (container)"
echo "   env      : ${TIME_TRACKER_ENV:-prod}"
echo "   database : $DB_PATH"
echo "   timezone : ${TIME_TRACKER_TIMEZONE:-<container default: UTC>}"
echo "   listening: http://${HOST}:${PORT}/"
echo "──────────────────────────────────────────────"

if [ -z "${TIME_TRACKER_TIMEZONE:-}" ]; then
    echo "⚠  TIME_TRACKER_TIMEZONE is unset; day grouping will use UTC." >&2
fi

exec python -m uvicorn app.main:app \
    --host "$HOST" \
    --port "$PORT" \
    --log-level "$LOG_LEVEL"
