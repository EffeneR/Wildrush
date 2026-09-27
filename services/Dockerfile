# syntax=docker/dockerfile:1
# WILDRUSH control service image (FastAPI + uvicorn, one process) — also carries the
# standard-library-only allocator agent (python -m allocator).
# Build context: services/   ->   docker build -t wildrush-control:1.0.0 services
# Base image pinned by tag + digest (Docker Hub, read 2026-09-27; not pulled/built in the
# authoring container, which has no Docker daemon — see docs/DEPLOYMENT.md).
FROM python:3.11.15-slim-trixie@sha256:90744cff8f32887f075c47d747a173ff333e9e98801667af93c357fa9f5e28ff

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN groupadd --system --gid 10001 wildrush \
 && useradd --system --uid 10001 --gid wildrush --home-dir /app --shell /usr/sbin/nologin wildrush

WORKDIR /app
COPY requirements-runtime.txt ./
RUN pip install --no-cache-dir -r requirements-runtime.txt

COPY alembic.ini ./
COPY alembic ./alembic
COPY wildrush_svc ./wildrush_svc
COPY allocator ./allocator

USER wildrush:wildrush
# Inside the container the service listens on all interfaces of the private compose
# network; only Caddy publishes ports (see deploy/docker-compose.yml).
ENV WR_BIND=0.0.0.0:8080
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"]
CMD ["python", "-m", "wildrush_svc", "serve"]
