"""Pydantic request/response schemas.

Wire format
-----------
Input accepts any ISO-8601 datetime. Naive values are interpreted in the
configured ``TIME_TRACKER_TIMEZONE``. Output is always ISO-8601 **with** the
local UTC offset, so the browser can render it verbatim.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import settings
from app.timeutils import format_duration, local_day, to_local, to_utc_naive


class TimeEntryBase(BaseModel):
    start_at: datetime
    end_at: datetime
    note: str = Field(default="", description="What was worked on")

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str) -> str:
        v = (v or "").strip()
        if len(v) > settings.max_note_length:
            raise ValueError(
                f"note must be at most {settings.max_note_length} characters"
            )
        return v

    @model_validator(mode="after")
    def _check_order(self) -> "TimeEntryBase":
        start = to_utc_naive(self.start_at, settings.tzinfo)
        end = to_utc_naive(self.end_at, settings.tzinfo)
        if end <= start:
            raise ValueError("end_at must be after start_at")
        return self


class TimeEntryCreate(TimeEntryBase):
    pass


class TimeEntryUpdate(BaseModel):
    """Partial update; unset fields are left untouched."""

    start_at: datetime | None = None
    end_at: datetime | None = None
    note: str | None = None

    @field_validator("note")
    @classmethod
    def _clean_note(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) > settings.max_note_length:
            raise ValueError(
                f"note must be at most {settings.max_note_length} characters"
            )
        return v


class TimeEntryRead(BaseModel):
    """Outbound representation: local-tz aware + computed duration."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    start_at: datetime
    end_at: datetime
    note: str
    duration_seconds: int
    duration_human: str
    day: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_local(cls, entry) -> "TimeEntryRead":  # noqa: ANN001
        tz = settings.tzinfo
        start_local = to_local(entry.start_at, tz)
        end_local = to_local(entry.end_at, tz)
        duration = entry.duration_seconds
        return cls(
            id=entry.id,
            start_at=start_local,
            end_at=end_local,
            note=entry.note or "",
            duration_seconds=duration,
            duration_human=format_duration(duration),
            day=local_day(entry.start_at, tz).isoformat(),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )


class DayGroup(BaseModel):
    day: str
    weekday: str
    entry_count: int
    total_seconds: int
    total_human: str
    entries: list[TimeEntryRead]


class EntriesByDayResponse(BaseModel):
    timezone: str
    total_seconds: int
    total_human: str
    entry_count: int
    days: list[DayGroup]


class SummaryResponse(BaseModel):
    timezone: str
    today: str
    today_seconds: int
    today_human: str
    today_count: int
    week_seconds: int
    week_human: str
    week_count: int
    all_time_seconds: int
    all_time_human: str
    all_time_count: int


class HealthResponse(BaseModel):
    status: str
    app: str
    env: str
    timezone: str
    db_path: str
    allow_overlap: bool
    entry_count: int
