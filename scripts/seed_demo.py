"""Populate the database with realistic demo entries.

    .venv/bin/python scripts/seed_demo.py            # add demo data
    .venv/bin/python scripts/seed_demo.py --clear    # wipe everything first

Entries are relative to *today* so the day-grouped view always looks alive.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

# Override to seed another instance, e.g. a container on a different port:
#   TIME_TRACKER_BASE_URL=http://127.0.0.1:8788 .venv/bin/python scripts/seed_demo.py
BASE = os.environ.get("TIME_TRACKER_BASE_URL", "http://127.0.0.1:8787")

# (days_ago, start HH:MM, duration in minutes, note)
PLAN: list[tuple[int, int, int, int, str]] = [
    (0, 9, 0, 30, "Standup + sprint planning"),
    (0, 9, 30, 105, "Auth refactor — token rotation"),
    (0, 11, 15, 45, "Code review: PR #142"),
    (0, 14, 0, 120, "Pairing on the billing webhook"),
    (1, 9, 15, 60, "Fix flaky integration tests"),
    (1, 11, 0, 180, "Data migration dry run"),
    (1, 14, 30, 90, "Write ADR: queue vs cron"),
    (2, 8, 30, 45, "Triage incoming bug reports"),
    (2, 10, 0, 150, "Dashboard performance work"),
    (3, 9, 0, 240, "Workshop: onboarding new hire"),
    (6, 13, 0, 165, "Retrospective + roadmap sync"),
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true", help="delete all entries first")
    args = parser.parse_args()

    client = httpx.Client(base_url=BASE, timeout=10.0, trust_env=False)

    try:
        client.get("/api/health").raise_for_status()
    except Exception:
        print(f"✖ Time Tracker is not reachable at {BASE}. Start it with ./run.sh")
        return 1

    if args.clear:
        existing = client.get("/api/entries", params={"limit": 2000}).json()
        for entry in existing:
            client.delete(f"/api/entries/{entry['id']}")
        print(f"cleared {len(existing)} existing entries")

    today = datetime.now().date()
    created = skipped = 0

    for days_ago, hour, minute, duration, note in PLAN:
        day = today - timedelta(days=days_ago)
        start = datetime(day.year, day.month, day.day, hour, minute)
        end = start + timedelta(minutes=duration)

        resp = client.post(
            "/api/entries",
            json={"start_at": start.isoformat(), "end_at": end.isoformat(), "note": note},
        )
        if resp.status_code == 201:
            created += 1
            data = resp.json()
            print(f"  + {data['day']}  {start:%H:%M}-{end:%H:%M}  "
                  f"{data['duration_human']:>7}  {note}")
        else:
            skipped += 1
            reason = resp.json().get("detail", resp.status_code)
            print(f"  · skipped {start:%Y-%m-%d %H:%M} ({note}): {reason}")

    print(f"\n{created} created, {skipped} skipped.")
    print(f"Open {BASE}/ to see them grouped by day.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
