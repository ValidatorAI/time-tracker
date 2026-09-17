"""API tests for the Time Tracker backend (timezone pinned to UTC)."""

from __future__ import annotations

from tests.conftest import make_entry


# ---------------------------------------------------------------- creation
def test_create_entry_returns_computed_fields(client):
    entry = make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T11:30:00Z", "Auth refactor")

    assert entry["note"] == "Auth refactor"
    assert entry["duration_seconds"] == 9000
    assert entry["duration_human"] == "2h 30m"
    assert entry["day"] == "2026-09-17"
    assert entry["start_at"].startswith("2026-09-17T09:00:00")


def test_create_rejects_end_before_start(client):
    resp = client.post(
        "/api/entries",
        json={"start_at": "2026-09-17T11:00:00Z", "end_at": "2026-09-17T10:00:00Z"},
    )
    assert resp.status_code == 422
    assert "end_at must be after start_at" in resp.json()["detail"]


def test_create_rejects_zero_length(client):
    resp = client.post(
        "/api/entries",
        json={"start_at": "2026-09-17T11:00:00Z", "end_at": "2026-09-17T11:00:00Z"},
    )
    assert resp.status_code == 422


def test_naive_datetime_is_interpreted_as_local(client):
    """No offset supplied -> treated as UTC here (TIME_TRACKER_TIMEZONE=UTC)."""
    entry = make_entry(client, "2026-09-17T08:00:00", "2026-09-17T09:00:00")
    assert entry["duration_seconds"] == 3600


# --------------------------------------------------------------- overlap
def test_overlapping_entry_is_rejected(client):
    make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:00:00Z")
    resp = client.post(
        "/api/entries",
        json={"start_at": "2026-09-17T09:30:00Z", "end_at": "2026-09-17T10:30:00Z"},
    )
    assert resp.status_code == 409
    assert "overlaps" in resp.json()["detail"]


def test_adjacent_entries_are_allowed(client):
    make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:00:00Z")
    resp = client.post(
        "/api/entries",
        json={"start_at": "2026-09-17T10:00:00Z", "end_at": "2026-09-17T11:00:00Z"},
    )
    assert resp.status_code == 201


def test_contained_overlap_is_rejected(client):
    make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T12:00:00Z")
    resp = client.post(
        "/api/entries",
        json={"start_at": "2026-09-17T10:00:00Z", "end_at": "2026-09-17T11:00:00Z"},
    )
    assert resp.status_code == 409


# ------------------------------------------------------ day grouping
def test_entries_grouped_by_day_descending(client):
    make_entry(client, "2026-09-15T09:00:00Z", "2026-09-15T10:00:00Z", "oldest")
    make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:30:00Z", "newest A")
    make_entry(client, "2026-09-17T14:00:00Z", "2026-09-17T15:00:00Z", "newest B")
    make_entry(client, "2026-09-16T08:00:00Z", "2026-09-16T08:15:00Z", "middle")

    payload = client.get("/api/entries/days").json()

    assert [d["day"] for d in payload["days"]] == [
        "2026-09-17",
        "2026-09-16",
        "2026-09-15",
    ]
    assert payload["entry_count"] == 4

    newest_day = payload["days"][0]
    assert newest_day["weekday"] == "Thursday"
    assert newest_day["entry_count"] == 2
    assert newest_day["total_seconds"] == 5400 + 3600
    assert newest_day["total_human"] == "2h 30m"
    # entries inside a day are newest-first too
    assert [e["note"] for e in newest_day["entries"]] == ["newest B", "newest A"]

    assert payload["total_seconds"] == 3600 + 5400 + 3600 + 900


def test_days_endpoint_filters_by_date_range(client):
    make_entry(client, "2026-09-15T09:00:00Z", "2026-09-15T10:00:00Z")
    make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:00:00Z")

    payload = client.get("/api/entries/days?start=2026-09-16").json()
    assert [d["day"] for d in payload["days"]] == ["2026-09-17"]

    payload = client.get("/api/entries/days?end=2026-09-16").json()
    assert [d["day"] for d in payload["days"]] == ["2026-09-15"]


# ------------------------------------------------------------ listing
def test_flat_list_is_newest_first_and_filterable(client):
    make_entry(client, "2026-09-15T09:00:00Z", "2026-09-15T10:00:00Z", "writing docs")
    make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:00:00Z", "fixing bug")

    entries = client.get("/api/entries").json()
    assert [e["note"] for e in entries] == ["fixing bug", "writing docs"]

    hits = client.get("/api/entries?q=docs").json()
    assert len(hits) == 1
    assert hits[0]["note"] == "writing docs"


def test_limit_and_offset(client):
    for i in range(5):
        make_entry(client, f"2026-09-17T0{i}:00:00Z", f"2026-09-17T0{i}:30:00Z", f"e{i}")

    page = client.get("/api/entries?limit=2&offset=1").json()
    assert [e["note"] for e in page] == ["e3", "e2"]


# ------------------------------------------------------------ update/delete
def test_patch_updates_note_and_times(client):
    entry = make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:00:00Z", "draft")

    resp = client.patch(
        f"/api/entries/{entry['id']}",
        json={"end_at": "2026-09-17T11:00:00Z", "note": "final"},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["note"] == "final"
    assert updated["duration_seconds"] == 7200


def test_patch_rejects_invalid_order(client):
    entry = make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:00:00Z")
    resp = client.patch(f"/api/entries/{entry['id']}", json={"end_at": "2026-09-17T08:00:00Z"})
    assert resp.status_code == 422


def test_patch_ignores_self_when_checking_overlap(client):
    entry = make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:00:00Z")
    resp = client.patch(f"/api/entries/{entry['id']}", json={"note": "same slot"})
    assert resp.status_code == 200


def test_delete_then_404(client):
    entry = make_entry(client, "2026-09-17T09:00:00Z", "2026-09-17T10:00:00Z")
    assert client.delete(f"/api/entries/{entry['id']}").status_code == 204
    assert client.get(f"/api/entries/{entry['id']}").status_code == 404
    assert client.get("/api/entries").json() == []
    assert client.delete("/api/entries/999").status_code == 404


# ----------------------------------------------------------------- summary
def test_summary_counts(client):
    make_entry(client, "2020-01-01T09:00:00Z", "2020-01-01T10:00:00Z", "ancient")

    payload = client.get("/api/entries/summary").json()
    assert payload["all_time_seconds"] == 3600
    assert payload["all_time_count"] == 1
    assert payload["today_count"] == 0


# ------------------------------------------------------------ meta/static
def test_health_and_config(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["allow_overlap"] is False

    cfg = client.get("/api/config").json()
    assert cfg["timezone"] == "UTC"
    assert cfg["max_note_length"] == 2000


def test_static_index_is_served(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Time Tracker" in resp.text
    assert "entryForm" in resp.text


def test_note_length_limit(client):
    resp = client.post(
        "/api/entries",
        json={
            "start_at": "2026-09-17T09:00:00Z",
            "end_at": "2026-09-17T10:00:00Z",
            "note": "x" * 2001,
        },
    )
    assert resp.status_code == 422
    assert "at most 2000" in resp.json()["detail"]
