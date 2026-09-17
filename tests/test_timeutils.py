"""Unit tests for the duration/timezone helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.timeutils import (
    format_duration,
    local_day,
    local_day_bounds,
    to_local,
    to_utc_naive,
)

TEHRAN = ZoneInfo("Asia/Tehran")  # UTC+03:30, no DST since 2022


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0m"),
        (30, "30s"),
        (59, "59s"),
        (60, "1m 00s"),
        (90, "1m 30s"),
        (3600, "1h 00m"),
        (9000, "2h 30m"),
        (5460, "1h 31m"),
        (-90, "-1m 30s"),
    ],
)
def test_format_duration(seconds, expected):
    assert format_duration(seconds) == expected


def test_to_utc_naive_treats_naive_input_as_local():
    # 09:00 Tehran == 05:30 UTC
    assert to_utc_naive(datetime(2026, 9, 17, 9, 0), TEHRAN) == datetime(2026, 9, 17, 5, 30)


def test_to_utc_naive_respects_explicit_offset():
    aware = datetime(2026, 9, 17, 9, 0, tzinfo=timezone.utc)
    assert to_utc_naive(aware, TEHRAN) == datetime(2026, 9, 17, 9, 0)


def test_to_local_roundtrip():
    utc = datetime(2026, 9, 17, 5, 30)
    local = to_local(utc, TEHRAN)
    assert local.hour == 9 and local.minute == 0
    assert local.utcoffset() == timedelta(hours=3, minutes=30)
    assert to_utc_naive(local, TEHRAN) == utc


def test_local_day_uses_local_midnight_not_utc():
    """20:30 UTC on the 17th is already 00:00 on the 18th in Tehran."""
    assert local_day(datetime(2026, 9, 17, 20, 30), TEHRAN) == date(2026, 9, 18)
    assert local_day(datetime(2026, 9, 17, 20, 29), TEHRAN) == date(2026, 9, 17)


def test_local_day_bounds_are_half_open_and_cover_exactly_one_day():
    start, end = local_day_bounds(date(2026, 9, 17), TEHRAN)
    assert start == datetime(2026, 9, 16, 20, 30)  # 00:00 Tehran -> UTC
    assert end == datetime(2026, 9, 17, 20, 30)
    assert end - start == timedelta(days=1)


def test_midnight_crossing_entry_belongs_to_start_day():
    start = datetime(2026, 9, 17, 23, 0)
    end = start + timedelta(hours=2)
    assert local_day(to_utc_naive(start, TEHRAN), TEHRAN) == date(2026, 9, 17)
    assert local_day(to_utc_naive(end, TEHRAN), TEHRAN) == date(2026, 9, 18)
