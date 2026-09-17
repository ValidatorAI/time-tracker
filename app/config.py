"""Application configuration, sourced entirely from environment variables.

Every setting is read through pydantic-settings with the ``TIME_TRACKER_``
prefix, so the whole app can be re-pointed (database location, port,
timezone, validation strictness...) without touching code.
"""

from __future__ import annotations

import os
from datetime import datetime, tzinfo
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def system_timezone() -> tzinfo:
    """Best-effort local timezone.

    Tries, in order: $TZ, /etc/localtime via ZoneInfo, then the OS-reported
    UTC offset (a fixed-offset tzinfo, which is good enough for day bucketing).
    """
    name = os.environ.get("TZ")
    if name:
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            pass

    localtime = Path("/etc/localtime")
    if localtime.is_symlink():
        target = str(localtime.resolve())
        if "zoneinfo/" in target:
            try:
                return ZoneInfo(target.split("zoneinfo/", 1)[1])
            except (ZoneInfoNotFoundError, ValueError):
                pass

    return datetime.now().astimezone().tzinfo or ZoneInfo("UTC")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TIME_TRACKER_",
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Time Tracker"
    env: str = "dev"
    host: str = "127.0.0.1"
    port: int = 8787
    log_level: str = "info"

    # The headline environment variable of this app.
    db_path: Path = Path("./data/time_tracker.db")

    # Empty string => auto-detect.
    timezone: str = ""
    allow_overlap: bool = False
    cors_origins: str = "*"
    max_note_length: int = 2000

    # ---- validators -------------------------------------------------
    @field_validator("db_path", mode="before")
    @classmethod
    def _default_db_path(cls, v: object) -> object:
        if v in (None, ""):
            return Path("./data/time_tracker.db")
        return v

    @field_validator("timezone", "log_level", mode="before")
    @classmethod
    def _none_to_empty(cls, v: object) -> object:
        """Treat unset vars as empty strings so the defaults stay meaningful."""
        return "" if v is None else v

    # ---- derived properties -----------------------------------------
    @property
    def is_dev(self) -> bool:
        return self.env.lower() in {"dev", "development", "local"}

    @property
    def resolved_db_path(self) -> Path:
        """Absolute database path (relative values are project-relative)."""
        raw = Path(self.db_path).expanduser()
        return raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()

    @property
    def database_url(self) -> str:
        return f"sqlite+pysqlite:///{self.resolved_db_path}"

    @property
    def tzinfo(self) -> tzinfo:
        if self.timezone:
            try:
                return ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError) as exc:  # pragma: no cover
                raise ValueError(
                    f"TIME_TRACKER_TIMEZONE={self.timezone!r} is not a valid IANA "
                    "timezone name (e.g. 'Europe/Berlin')."
                ) from exc
        return system_timezone()

    @property
    def tzlabel(self) -> str:
        return self.timezone or getattr(self.tzinfo, "key", None) or str(self.tzinfo)

    @property
    def cors_origin_list(self) -> list[str]:
        raw = (self.cors_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
