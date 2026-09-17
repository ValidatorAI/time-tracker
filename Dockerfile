# syntax=docker/dockerfile:1

# ═══════════════════════════════════════════════════════════════════════════
#  Stage 1 — compile the Tailwind stylesheet
#
#  Only the files Tailwind scans are copied in, so this layer stays cached
#  until the markup, the JS or the Tailwind config actually changes.
# ═══════════════════════════════════════════════════════════════════════════
FROM node:22-alpine AS css

WORKDIR /build

COPY package.json package-lock.json tailwind.config.js ./
COPY src/input.css ./src/input.css
COPY static/index.html ./static/index.html
COPY static/js/ ./static/js/

# `npm ci` honours the lockfile, so the build is reproducible.
RUN npm ci --no-audit --no-fund \
    && npx tailwindcss -i ./src/input.css -o ./static/css/tailwind.css --minify


# ═══════════════════════════════════════════════════════════════════════════
#  Stage 2 — runtime
# ═══════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Optional build-time proxy. Declared (with no default) so the value is only in
# the environment when the caller actually passes one — an empty http_proxy can
# confuse some clients. Needed on networks where PyPI is only reachable through
# a proxy, e.g.:
#
#   docker build --network=host \
#     --build-arg http_proxy=http://127.0.0.1:10808 \
#     --build-arg https_proxy=http://127.0.0.1:10808 .
#
# --network=host matters: a proxy bound to the host's 127.0.0.1 is not reachable
# from the default bridge network during a build. Left unset, the build simply
# goes direct.
ARG http_proxy
ARG https_proxy
ARG no_proxy

# Dependencies before source: this layer is only rebuilt when requirements change.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/

# Overwrite whatever CSS came from the context with the freshly compiled one.
COPY --from=css /build/static/css/tailwind.css ./static/css/tailwind.css

COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/time-tracker-entrypoint

# Non-root user, and a data directory it owns. Creating /data *before* the
# VOLUME declaration matters: Docker seeds a new named volume with the image's
# files at that path, ownership included, so the non-root user can write to it.
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser \
    && mkdir -p /data \
    && chown -R appuser:appuser /data /app
USER appuser

# Baked-in defaults. All of them are ordinary environment variables, so
# `-e` / compose `environment:` override them without touching the image.
ENV TIME_TRACKER_HOST=0.0.0.0 \
    TIME_TRACKER_PORT=8787 \
    TIME_TRACKER_DB_PATH=/data/time_tracker.db \
    TIME_TRACKER_ENV=prod

VOLUME ["/data"]
EXPOSE 8787
STOPSIGNAL SIGTERM

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('TIME_TRACKER_PORT','8787')+'/api/health',timeout=3)"

ENTRYPOINT ["/usr/local/bin/time-tracker-entrypoint"]
