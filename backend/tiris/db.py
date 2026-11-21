"""Connection pool and SQL migrations (plain files in tiris/migrations, applied once, in order)."""
from __future__ import annotations

import logging
from importlib import resources

import psycopg
from psycopg_pool import ConnectionPool

log = logging.getLogger("tiris.db")

_pool: ConnectionPool | None = None


def open_pool(url: str) -> ConnectionPool:
    global _pool
    _pool = ConnectionPool(url, min_size=1, max_size=10, open=True, kwargs={"autocommit": False})
    return _pool


def pool() -> ConnectionPool:
    if _pool is None:
        raise RuntimeError("database pool not opened")
    return _pool


def close_pool() -> None:
    if _pool is not None:
        _pool.close()


def migrate(url: str) -> list[str]:
    """Apply pending migrations. Each file runs in its own transaction; returns the applied names."""
    files = sorted(p for p in resources.files("tiris.migrations").iterdir() if p.name.endswith(".sql"))
    applied: list[str] = []
    with psycopg.connect(url, autocommit=True) as con:
        con.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY, "
                    "applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
        done = {r[0] for r in con.execute("SELECT name FROM schema_migrations")}
        for f in files:
            if f.name in done:
                continue
            log.info("applying migration %s", f.name)
            with con.transaction():
                con.execute(f.read_text(encoding="utf-8"))
                con.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (f.name,))
            applied.append(f.name)
    return applied
