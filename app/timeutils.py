"""Timezone helpers: naive-UTC storage <-> local-tz presentation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone, tzinfo


def to_utc_naive(value: datetime, local_tz: tzinfo) -> datetime:
    """Normalise any incoming datetime to naive UTC.

    Naive input is interpreted as local time in ``local_tz`` (the frontend
    sends ``datetime-local`` values, which carry no offset).
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_tz)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def to_local(value: datetime, local_tz: tzinfo) -> datetime:
    """Turn a naive-UTC database value into an aware local datetime."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(local_tz)


def local_day(value: datetime, local_tz: tzinfo) -> date:
    """Calendar day (in ``local_tz``) that a naive-UTC timestamp falls on."""
    return to_local(value, local_tz).date()


def local_day_bounds(day: date, local_tz: tzinfo) -> tuple[datetime, datetime]:
    """Naive-UTC [start, end) range covering one local calendar day."""
    start = datetime.combine(day, datetime.min.time(), tzinfo=local_tz)
    end = start + timedelta(days=1)
    return (
        start.astimezone(timezone.utc).replace(tzinfo=None),
        end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def format_duration(seconds: int | float) -> str:
    """Human-readable duration, e.g. 2h 05m / 45m / 30s."""
    total = int(round(seconds))
    if total == 0:
        return "0m"
    sign = "-" if total < 0 else ""
    total = abs(total)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{sign}{hours}h {minutes:02d}m"
    if minutes:
        return f"{sign}{minutes}m {secs:02d}s"
    return f"{sign}{secs}s"
