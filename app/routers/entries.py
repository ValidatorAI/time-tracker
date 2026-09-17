"""CRUD + reporting endpoints for time entries."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import TimeEntry
from app.schemas import (
    DayGroup,
    EntriesByDayResponse,
    SummaryResponse,
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntryUpdate,
)
from app.timeutils import (
    format_duration,
    local_day,
    local_day_bounds,
    to_local,
    to_utc_naive,
)

router = APIRouter(prefix="/api", tags=["time-entries"])

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _get_or_404(db: Session, entry_id: int) -> TimeEntry:
    entry = db.get(TimeEntry, entry_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Time entry {entry_id} not found",
        )
    return entry


def _ensure_no_overlap(
    db: Session,
    start_utc: datetime,
    end_utc: datetime,
    *,
    exclude_id: int | None = None,
) -> None:
    """Reject an entry that overlaps an existing one (when configured)."""
    if settings.allow_overlap:
        return

    stmt = select(TimeEntry).where(
        TimeEntry.start_at < end_utc,
        TimeEntry.end_at > start_utc,
    )
    if exclude_id is not None:
        stmt = stmt.where(TimeEntry.id != exclude_id)

    clash = db.scalars(stmt.order_by(TimeEntry.start_at).limit(1)).first()
    if clash is None:
        return

    tz = settings.tzinfo
    c_start = to_local(clash.start_at, tz).strftime("%Y-%m-%d %H:%M")
    c_end = to_local(clash.end_at, tz).strftime("%H:%M")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=(
            f"This range overlaps entry #{clash.id} "
            f"({c_start} – {c_end}). Set TIME_TRACKER_ALLOW_OVERLAP=true to permit overlaps."
        ),
    )


def _stats(db: Session, start_utc: datetime | None, end_utc: datetime | None) -> tuple[int, int]:
    """Return (total_seconds, entry_count) for an optional UTC window."""
    stmt = select(
        func.count(TimeEntry.id),
        func.coalesce(func.sum(func.julianday(TimeEntry.end_at) - func.julianday(TimeEntry.start_at)), 0.0),
    )
    if start_utc is not None:
        stmt = stmt.where(TimeEntry.start_at >= start_utc)
    if end_utc is not None:
        stmt = stmt.where(TimeEntry.start_at < end_utc)

    count, days = db.execute(stmt).one()
    return int(round(float(days) * 86400)), int(count or 0)


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------
@router.get("/entries", response_model=list[TimeEntryRead])
def list_entries(
    db: Session = Depends(get_db),
    start: date | None = Query(None, description="Only entries on/after this local date"),
    end: date | None = Query(None, description="Only entries before this local date"),
    q: str | None = Query(None, description="Substring match on note"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
) -> list[TimeEntryRead]:
    """Flat list of entries, newest first."""
    stmt = select(TimeEntry)

    if start is not None:
        stmt = stmt.where(TimeEntry.start_at >= local_day_bounds(start, settings.tzinfo)[0])
    if end is not None:
        stmt = stmt.where(TimeEntry.start_at < local_day_bounds(end, settings.tzinfo)[0])
    if q:
        stmt = stmt.where(TimeEntry.note.ilike(f"%{q}%"))

    stmt = stmt.order_by(TimeEntry.start_at.desc(), TimeEntry.id.desc())
    stmt = stmt.limit(limit).offset(offset)

    return [TimeEntryRead.from_orm_local(e) for e in db.scalars(stmt).all()]


@router.get("/entries/days", response_model=EntriesByDayResponse)
def entries_grouped_by_day(
    db: Session = Depends(get_db),
    start: date | None = Query(None, description="Only days on/after this local date"),
    end: date | None = Query(None, description="Only days on/before this local date"),
    gap_fill: bool = Query(False, description="Include empty days between start and end"),
) -> EntriesByDayResponse:
    """Entries bucketed by local calendar day, days descending.

    This is the endpoint the UI's day-grouped list uses.
    """
    tz = settings.tzinfo

    stmt = select(TimeEntry).order_by(TimeEntry.start_at.desc(), TimeEntry.id.desc())
    if start is not None:
        stmt = stmt.where(TimeEntry.start_at >= local_day_bounds(start, tz)[0])
    if end is not None:
        stmt = stmt.where(TimeEntry.start_at < local_day_bounds(end, tz)[0])

    all_entries = db.scalars(stmt).all()

    buckets: dict[date, list[TimeEntry]] = defaultdict(list)
    for entry in all_entries:
        buckets[local_day(entry.start_at, tz)].append(entry)

    days: list[DayGroup] = []
    keys = sorted(buckets.keys(), reverse=True)

    for key in keys:
        items = buckets[key]
        total = sum(e.duration_seconds for e in items)
        days.append(
            DayGroup(
                day=key.isoformat(),
                weekday=WEEKDAY_NAMES[key.weekday()],
                entry_count=len(items),
                total_seconds=total,
                total_human=format_duration(total),
                entries=[TimeEntryRead.from_orm_local(e) for e in items],
            )
        )

    grand_total = sum(d.total_seconds for d in days)
    return EntriesByDayResponse(
        timezone=settings.tzlabel,
        total_seconds=grand_total,
        total_human=format_duration(grand_total),
        entry_count=len(all_entries),
        days=days,
    )


@router.get("/entries/summary", response_model=SummaryResponse)
def summary(db: Session = Depends(get_db)) -> SummaryResponse:
    """Totals for today, the current week (Mon–Sun) and all time."""
    tz = settings.tzinfo
    today = datetime.now(tz).date()
    week_start = today - timedelta(days=today.weekday())

    today_start, today_end = local_day_bounds(today, tz)
    week_start_utc, _ = local_day_bounds(week_start, tz)

    today_seconds, today_count = _stats(db, today_start, today_end)
    week_seconds, week_count = _stats(db, week_start_utc, None)
    all_seconds, all_count = _stats(db, None, None)

    return SummaryResponse(
        timezone=settings.tzlabel,
        today=today.isoformat(),
        today_seconds=today_seconds,
        today_human=format_duration(today_seconds),
        today_count=today_count,
        week_seconds=week_seconds,
        week_human=format_duration(week_seconds),
        week_count=week_count,
        all_time_seconds=all_seconds,
        all_time_human=format_duration(all_seconds),
        all_time_count=all_count,
    )


@router.post("/entries", response_model=TimeEntryRead, status_code=status.HTTP_201_CREATED)
def create_entry(payload: TimeEntryCreate, db: Session = Depends(get_db)) -> TimeEntryRead:
    tz = settings.tzinfo
    start_utc = to_utc_naive(payload.start_at, tz)
    end_utc = to_utc_naive(payload.end_at, tz)
    _ensure_no_overlap(db, start_utc, end_utc)

    entry = TimeEntry(start_at=start_utc, end_at=end_utc, note=payload.note)
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return TimeEntryRead.from_orm_local(entry)


@router.get("/entries/{entry_id}", response_model=TimeEntryRead)
def get_entry(entry_id: int, db: Session = Depends(get_db)) -> TimeEntryRead:
    return TimeEntryRead.from_orm_local(_get_or_404(db, entry_id))


@router.patch("/entries/{entry_id}", response_model=TimeEntryRead)
def update_entry(
    entry_id: int, payload: TimeEntryUpdate, db: Session = Depends(get_db)
) -> TimeEntryRead:
    entry = _get_or_404(db, entry_id)
    tz = settings.tzinfo

    new_start = to_utc_naive(payload.start_at, tz) if payload.start_at else entry.start_at
    new_end = to_utc_naive(payload.end_at, tz) if payload.end_at else entry.end_at

    if new_end <= new_start:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="end_at must be after start_at",
        )

    _ensure_no_overlap(db, new_start, new_end, exclude_id=entry.id)

    entry.start_at = new_start
    entry.end_at = new_end
    if payload.note is not None:
        entry.note = payload.note

    db.commit()
    db.refresh(entry)
    return TimeEntryRead.from_orm_local(entry)


@router.delete(
    "/entries/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    response_model=None,
)
def delete_entry(entry_id: int, db: Session = Depends(get_db)) -> None:
    entry = _get_or_404(db, entry_id)
    db.delete(entry)
    db.commit()


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    count = db.scalar(select(func.count(TimeEntry.id))) or 0
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.env,
        "timezone": settings.tzlabel,
        "db_path": str(settings.resolved_db_path),
        "allow_overlap": settings.allow_overlap,
        "entry_count": int(count),
    }
