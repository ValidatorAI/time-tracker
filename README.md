# Time Tracker

A small self-hosted time tracker. Log what you worked on with a **start datetime,
an end datetime and a note**, then review it **grouped by day, newest day first**.

- **Backend:** Python + FastAPI + SQLAlchemy 2.0 (SQLite)
- **Frontend:** jQuery 3.7 + Tailwind CSS 3.4 — no build step needed at runtime,
  both are vendored locally so the app works completely offline
- **Config:** every setting comes from `TIME_TRACKER_*` environment variables

---

## Quick start

```bash
cd ~/time-tracker
./run.sh                     # creates the venv on first run, then starts uvicorn
```

Then open <http://127.0.0.1:8787/>.

- API docs (Swagger UI): <http://127.0.0.1:8787/docs>
- `./run.sh --no-reload` disables the dev auto-reloader

Want some sample data to look at?

```bash
.venv/bin/python scripts/seed_demo.py --clear
```

---

## What the UI gives you

| Area | Behaviour |
| --- | --- |
| Summary cards | Today / this week (Mon–Sun) / all-time totals |
| Filters | From-date, to-date, and note search; change a date to auto-apply |
| Day groups | One card per calendar day, **days descending**, each with the day's total and entry count. Days are labelled "Today"/"Yesterday" when relevant |
| Rows | Start–end times, full range tooltip, duration badge, note, hover-revealed edit/delete |
| **New entry modal** | Start + end `datetime-local` pickers, note textarea with character counter, live duration preview, quick buttons (`Last hour`, `Since 09:00`, `End = now`) |
| Errors | Server messages surface verbatim — an overlap clash tells you which entry it hits and how to allow overlaps |
| Keyboard | `Escape` closes the topmost dialog, `Ctrl`/`Cmd`+`Enter` saves |

---

## Environment variables

All settings use the `TIME_TRACKER_` prefix and are read from `.env`.
Copy `.env.example` to `.env` and edit.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TIME_TRACKER_DB_PATH` | `./data/time_tracker.db` | **The headline variable.** Where your tracked time is stored. Relative paths resolve against the project root |
| `TIME_TRACKER_TIMEZONE` | auto-detect | IANA name (e.g. `Asia/Tehran`) used to decide which calendar day an entry belongs to. Empty = detect from `/etc/localtime` |
| `TIME_TRACKER_HOST` | `127.0.0.1` | Bind address |
| `TIME_TRACKER_PORT` | `8787` | Bind port |
| `TIME_TRACKER_ENV` | `dev` | `dev` enables auto-reload, verbose errors and no-cache static files |
| `TIME_TRACKER_LOG_LEVEL` | `info` | uvicorn log level |
| `TIME_TRACKER_ALLOW_OVERLAP` | `false` | `false` rejects entries overlapping an existing one with HTTP 409 |
| `TIME_TRACKER_CORS_ORIGINS` | `*` | Comma-separated origins, or `*` |
| `TIME_TRACKER_MAX_NOTE_LENGTH` | `2000` | Note length ceiling |

Example — keep the database somewhere durable and move the port:

```bash
export TIME_TRACKER_DB_PATH=/var/lib/time-tracker/time_tracker.db
export TIME_TRACKER_PORT=9000
./run.sh
```

---

## API

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/health` | Liveness + resolved config + entry count |
| `GET` | `/api/config` | Client-visible settings |
| `GET` | `/api/entries/days` | **Day-grouped view**, days descending. Query: `start`, `end`, `gap_fill` |
| `GET` | `/api/entries/summary` | Today / this week / all-time totals |
| `GET` | `/api/entries` | Flat list, newest first. Query: `start`, `end`, `q`, `limit`, `offset` |
| `POST` | `/api/entries` | Create — `{start_at, end_at, note}` → `201` |
| `GET` | `/api/entries/{id}` | Single entry |
| `PATCH` | `/api/entries/{id}` | Partial update of any of `start_at` / `end_at` / `note` |
| `DELETE` | `/api/entries/{id}` | Delete → `204` |

### Timezones

Timestamps are stored as **naive UTC**. Input may be any ISO-8601 string;
a value *without* an offset is interpreted in `TIME_TRACKER_TIMEZONE`. Output is
always ISO-8601 **with** the local UTC offset. The browser sends
`new Date(localValue).toISOString()`, so what you type is what you see.

### Status codes

- `422` — `end_at` is not after `start_at`, unparseable datetime, or note too long
- `409` — the range overlaps an existing entry (skipped when `TIME_TRACKER_ALLOW_OVERLAP=true`)
- `404` — no such entry

`end_at <= start_at` is validated **before** the overlap check, so an inverted
range reports `422` rather than `409`.

---

## Development

```bash
.venv/bin/python -m pytest                    # 34 tests (TestClient + timeutils units)
.venv/bin/python scripts/verify_api.py        # 21 checks against a *running* server
npm run watch:css                             # rebuild Tailwind while editing the UI
```

Tests run against an isolated temp database and pin the timezone to UTC, so they
are independent of your machine's clock settings.

### Layout

```
time-tracker/
├── app/
│   ├── config.py          env-var settings (pydantic-settings)
│   ├── database.py        engine, session, init_db
│   ├── models.py          TimeEntry ORM model
│   ├── schemas.py         request/response models + validation
│   ├── timeutils.py       UTC <-> local conversion, duration formatting
│   ├── main.py            app factory, CORS, error handler, static mount
│   └── routers/entries.py all endpoints incl. day grouping
├── static/
│   ├── index.html         markup + row/day templates
│   ├── js/app.js          jQuery UI logic
│   ├── css/tailwind.css   compiled (checked in, no runtime build)
│   └── vendor/jquery.min.js
├── src/input.css          Tailwind source
├── scripts/
│   ├── seed_demo.py       demo data
│   └── verify_api.py      live-server smoke test
├── tests/
│   ├── conftest.py        isolated temp DB, UTC-pinned settings
│   ├── test_entries.py    API behaviour
│   └── test_timeutils.py  duration formatting + timezone bucketing
├── run.sh                 launcher
├── tailwind.config.js
├── package.json           Tailwind build tooling only
└── .env / .env.example
```

### Changing styles

Tailwind is compiled ahead of time into `static/css/tailwind.css`. After editing
`index.html` or `app.js`, rebuild:

```bash
npm run build:css      # one-off, minified
npm run watch:css      # during development
```

In `dev` mode static responses carry `Cache-Control: no-store`, so a plain
browser reload always picks up your changes.

---

## Notes and limits

- Single user, no authentication — bind to `127.0.0.1` (the default) unless you
  deliberately put it behind a reverse proxy with auth.
- SQLite + WAL is plenty for personal use; for multi-user deployment swap
  `TIME_TRACKER_DB_PATH` handling in `app/database.py` for Postgres.
- Entries are stored per calendar day in your configured timezone. An entry that
  runs past midnight (e.g. 23:00–01:00) is grouped under its **start** day and
  shows its end time with a date, but is not split across both days.
- There is no "running timer" — you enter start and end explicitly, which keeps
  the data model honest and avoids a forgotten timer corrupting your history.
