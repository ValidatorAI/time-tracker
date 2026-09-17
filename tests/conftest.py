"""Shared pytest fixtures.

Environment is configured *before* importing the app so the settings
singleton picks up the isolated test database.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="time-tracker-tests-"))

os.environ["TIME_TRACKER_DB_PATH"] = str(_TMP / "test.db")
os.environ["TIME_TRACKER_TIMEZONE"] = "UTC"          # deterministic buckets
os.environ["TIME_TRACKER_ALLOW_OVERLAP"] = "false"
os.environ["TIME_TRACKER_ENV"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _cleanup_tmp() -> None:
    yield
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture
def client() -> TestClient:
    """Fresh schema + a TestClient with lifespan startup executed."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


def make_entry(client: TestClient, start: str, end: str, note: str = "") -> dict:
    resp = client.post(
        "/api/entries",
        json={"start_at": start, "end_at": end, "note": note},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()
