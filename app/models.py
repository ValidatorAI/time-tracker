"""ORM models.

Timestamps are stored as *naive UTC* in the database. All user-facing
input/output is timezone-aware ISO-8601; conversion happens in the schema
layer so the storage format stays unambiguous.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Naive UTC on purpose: SQLite has no tz-aware type.
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    note: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
        onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None),
    )

    __table_args__ = (
        Index("ix_time_entries_start_at", "start_at"),
        Index("ix_time_entries_end_at", "end_at"),
    )

    @property
    def duration_seconds(self) -> int:
        """Single source of truth for an entry's length."""
        return int((self.end_at - self.start_at).total_seconds())

    def __repr__(self) -> str:  # pragma: no cover
        return f"<TimeEntry id={self.id} start={self.start_at} end={self.end_at}>"


__all__ = ["TimeEntry"]
