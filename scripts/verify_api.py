"""End-to-end verification against the *running* Time Tracker server.

Not part of the pytest suite — this hits a real uvicorn instance over HTTP.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import httpx

# Override to point the suite at another instance, e.g. a container:
#   TIME_TRACKER_BASE_URL=http://127.0.0.1:8788 .venv/bin/python scripts/verify_api.py
BASE = os.environ.get("TIME_TRACKER_BASE_URL", "http://127.0.0.1:8787")
ok = 0
fail = 0


def check(label: str, condition: bool, extra: str = "") -> None:
    global ok, fail
    if condition:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fail += 1
        print(f"  FAIL  {label}  {extra}")


def iso(dt: datetime) -> str:
    return dt.isoformat()


# trust_env=False keeps ambient http_proxy/all_proxy settings out of the way:
# this script only ever talks to localhost, where a proxy is never wanted.
c = httpx.Client(base_url=BASE, timeout=10.0, trust_env=False)

print("=" * 74)
print(" 0. baseline")
print("=" * 74)
for e in c.get("/api/entries", params={"limit": 2000}).json():
    c.delete(f"/api/entries/{e['id']}")
print(f"  cleared -> entry_count={c.get('/api/health').json()['entry_count']}")

tz = c.get("/api/config").json()["timezone"]
print(f"  server timezone: {tz}")

# The server's "today", used to build realistic local wall-clock times.
today = datetime.now().date()


def slot(day, hour, minute, minutes_long):  # noqa: ANN001, ANN201
    """(start, end) as naive local datetimes on ``day``."""
    start = datetime(day.year, day.month, day.day, hour, minute)
    return start, start + timedelta(minutes=minutes_long)


print()
print("=" * 74)
print(" 1. create entries (naive local wall-clock times, as the browser sends)")
print("=" * 74)
seed = [
    (today, 9, 0, 90, "Standup + sprint planning"),
    (today, 11, 0, 150, "Auth refactor — token rotation"),
    (today - timedelta(days=1), 10, 15, 60, "Code review: PR #142"),
    (today - timedelta(days=1), 14, 0, 210, "Fix flaky integration tests"),
    (today - timedelta(days=2), 8, 30, 45, "Write ADR for the queue choice"),
]
created = []
for d, h, m, dur, note in seed:
    s, e = slot(d, h, m, dur)
    r = c.post("/api/entries", json={"start_at": iso(s), "end_at": iso(e), "note": note})
    if r.status_code != 201:
        print(f"  FAIL  create {note!r}: {r.status_code} {r.text}")
        fail += 1
        continue
    created.append(r.json())
    print(f"  {r.status_code} #{r.json()['id']:>3}  {note[:38]:38}  "
          f"{r.json()['duration_human']:>7}  day={r.json()['day']}")
check("created 5 entries", len(created) == 5, f"got {len(created)}")

print()
print("=" * 74)
print(" 2. validation")
print("=" * 74)
s, e = slot(today, 18, 0, -60)  # end before start
r = c.post("/api/entries", json={"start_at": iso(s), "end_at": iso(e), "note": "backwards"})
check("end<start -> 422", r.status_code == 422, f"got {r.status_code}")
print(f"        detail: {r.json().get('detail')}")

s, e = slot(today, 12, 0, 30)  # overlaps the 11:00-13:30 entry
r = c.post("/api/entries", json={"start_at": iso(s), "end_at": iso(e), "note": "clash"})
check("overlap -> 409", r.status_code == 409, f"got {r.status_code}")
print(f"        detail: {r.json().get('detail')}")

s, e = slot(today, 13, 30, 30)  # touches the previous entry exactly
r = c.post("/api/entries", json={"start_at": iso(s), "end_at": iso(e), "note": "adjacent"})
check("adjacent (13:30) -> 201", r.status_code == 201, f"got {r.status_code}")
adjacent_id = r.json()["id"] if r.status_code == 201 else None

r = c.post("/api/entries", json={"start_at": iso(s), "end_at": iso(e), "note": "x" * 2001})
check("note > max -> 422", r.status_code == 422, f"got {r.status_code}")

r = c.post("/api/entries", json={"start_at": "not-a-date", "end_at": iso(e)})
check("unparseable date -> 422", r.status_code == 422, f"got {r.status_code}")

print()
print("=" * 74)
print(" 3. GET /api/entries/days  <- the day-grouped view the UI renders")
print("=" * 74)
payload = c.get("/api/entries/days").json()
print(f"  timezone       : {payload['timezone']}")
print(f"  total          : {payload['total_human']} over {payload['entry_count']} entries")
print(f"  days returned  : {[d['day'] for d in payload['days']]}")
print()
for day in payload["days"]:
    print(f"  ┌─ {day['weekday']}, {day['day']}   "
          f"total={day['total_human']}  ({day['entry_count']} entries)")
    for en in day["entries"]:
        st = en["start_at"][11:16]
        et = en["end_at"][11:16]
        print(f"  │   {st}-{et}  {en['duration_human']:>7}  {en['note']}")
    print("  └" + "─" * 68)

days_iso = [d["day"] for d in payload["days"]]
check("days sorted descending", days_iso == sorted(days_iso, reverse=True), str(days_iso))
check("3 distinct days", len(days_iso) == 3, str(days_iso))
check("day totals are human-formatted",
      all("h" in d["total_human"] or "m" in d["total_human"] for d in payload["days"]))

print()
print("=" * 74)
print(" 4. summary")
print("=" * 74)
summary = c.get("/api/entries/summary").json()
print(f"  today     : {summary['today_human']}  ({summary['today_count']} entries)")
print(f"  this week : {summary['week_human']}  ({summary['week_count']} entries)")
print(f"  all time  : {summary['all_time_human']}  ({summary['all_time_count']} entries)")
check("summary all_time_count matches", summary["all_time_count"] == payload["entry_count"])

print()
print("=" * 74)
print(" 5. update / delete")
print("=" * 74)
target = created[0]
r = c.patch(f"/api/entries/{created[0]['id']}", json={"note": "Standup + planning (edited)"})
check("PATCH note -> 200", r.status_code == 200, f"got {r.status_code}")
check("note updated", r.json()["note"] == "Standup + planning (edited)")

# Extending #1 to 11:30 collides with #2 (11:00-13:30) -> 409 is correct.
r = c.patch(f"/api/entries/{created[0]['id']}",
            json={"end_at": iso(datetime(today.year, today.month, today.day, 11, 30))})
check("PATCH into an existing overlap -> 409", r.status_code == 409, f"got {r.status_code}")

# #5 sits on 2026-09-15 08:30-09:15 with nothing after it: extending is fine.
r = c.patch(f"/api/entries/{created[4]['id']}",
            json={"end_at": iso(datetime((today - timedelta(days=2)).year,
                                         (today - timedelta(days=2)).month,
                                         (today - timedelta(days=2)).day, 10, 15))})
check("PATCH extend (free slot) -> 200", r.status_code == 200, f"got {r.status_code}")
check("extended duration is 1h 45m", r.json()["duration_human"] == "1h 45m",
      r.json().get("duration_human"))

# Moving #4's start to 11:00 overlaps #3 (10:15-11:15) while staying before its end.
d1 = today - timedelta(days=1)
r = c.patch(f"/api/entries/{created[3]['id']}",
            json={"start_at": iso(datetime(d1.year, d1.month, d1.day, 11, 0))})
check("PATCH shifting into overlap -> 409", r.status_code == 409, f"got {r.status_code}")

# end-before-start is checked first, so it reports 422 rather than 409.
r = c.patch(f"/api/entries/{created[1]['id']}",
            json={"end_at": iso(datetime(today.year, today.month, today.day, 10, 0))})
check("PATCH end<start -> 422", r.status_code == 422, f"got {r.status_code}")

if adjacent_id:
    r = c.delete(f"/api/entries/{adjacent_id}")
    check("DELETE -> 204", r.status_code == 204, f"got {r.status_code}")

r = c.get("/api/entries/999999")
check("GET missing -> 404", r.status_code == 404, f"got {r.status_code}")

r = c.get("/api/entries", params={"q": "review"})
check("note search finds 1", len(r.json()) == 1, f"got {len(r.json())}")

r = c.get("/api/entries/days", params={"start": (today - timedelta(days=1)).isoformat()})
check("date-range filter", len(r.json()["days"]) == 2, str([d["day"] for d in r.json()["days"]]))

print()
print("=" * 74)
print(f" RESULT: {ok} passed, {fail} failed")
print("=" * 74)
raise SystemExit(1 if fail else 0)
