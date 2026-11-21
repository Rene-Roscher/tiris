# syntax=docker/dockerfile:1
# Backend image. The web UI stage is added in phase 2 (see docs/PLAN.md).
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TIRIS_HOST=0.0.0.0 TIRIS_PORT=8080
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./backend/
COPY backend/tiris ./backend/tiris
RUN pip install ./backend && useradd --system --no-create-home tiris
USER tiris
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"TIRIS_PORT\",\"8080\")}/api/health', timeout=4)"
CMD ["python", "-c", "from tiris.main import run; run()"]
