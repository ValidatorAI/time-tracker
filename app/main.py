"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import PROJECT_ROOT, settings
from app.database import init_db
from app.routers import entries

STATIC_DIR = PROJECT_ROOT / "static"

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("time_tracker")


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    init_db()
    log.info("Time Tracker starting — env=%s db=%s tz=%s",
             settings.env, settings.resolved_db_path, settings.tzlabel)
    log.info("UI available at http://%s:%s/", settings.host, settings.port)
    yield
    log.info("Time Tracker stopped.")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Track worked time and review it grouped by day.",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(entries.router)


@app.middleware("http")
async def no_cache_static_in_dev(request: Request, call_next):  # noqa: ANN001
    """In dev, stop the browser from caching index.html/app.js/tailwind.css.

    Without this you edit a file, reload, and stare at stale output — which is
    exactly the trap the ?v= querystring in index.html only half-solves.
    """
    response = await call_next(request)
    if settings.is_dev and not request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Flatten FastAPI's validation errors into a single readable message."""
    problems: list[str] = []
    details: list[dict] = []

    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query"))
        msg = err.get("msg", "invalid value")
        problems.append(f"{loc}: {msg}" if loc else msg)

        # ``ctx`` may hold non-JSON-serialisable objects (e.g. ValueError),
        # so rebuild a safe payload instead of echoing exc.errors() verbatim.
        detail = {"type": err.get("type"), "loc": list(err.get("loc", ())), "msg": msg}
        details.append(detail)

    return JSONResponse(
        status_code=422,
        content={"detail": "; ".join(problems) or "Invalid request", "errors": details},
    )


@app.get("/api/config", tags=["meta"])
def public_config() -> dict:
    """Client-visible runtime settings (no secrets)."""
    return {
        "app": settings.app_name,
        "env": settings.env,
        "timezone": settings.tzlabel,
        "allow_overlap": settings.allow_overlap,
        "max_note_length": settings.max_note_length,
    }


# Static SPA (index.html served at /). Mounted last so /api/* and /docs win;
# StaticFiles(check_dir=True) fails loudly at import if static/ is missing.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True, check_dir=True), name="static")


def main() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_dev,
        log_level=settings.log_level,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
