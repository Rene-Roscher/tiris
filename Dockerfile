# syntax=docker/dockerfile:1
# Stage 1: web UI
FROM node:22-alpine AS web
WORKDIR /web
RUN corepack enable
COPY web/package.json web/pnpm-lock.yaml web/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY web/ ./
RUN pnpm exec vite build

# Stage 2: runtime (API, collector, live poller, built UI)
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TIRIS_HOST=0.0.0.0 TIRIS_PORT=8080 TIRIS_STATIC_DIR=/app/web
WORKDIR /app
COPY backend/pyproject.toml ./backend/
COPY backend/tiris ./backend/tiris
RUN pip install ./backend && useradd --system --no-create-home tiris
COPY --from=web /web/dist /app/web
USER tiris
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"TIRIS_PORT\",\"8080\")}/api/health', timeout=4)"
CMD ["python", "-c", "from tiris.main import run; run()"]
