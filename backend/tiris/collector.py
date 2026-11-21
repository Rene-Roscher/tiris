"""History collection: runs every few minutes, discovers plugs and stores hourly, daily, monthly energy and the
5-minute power buffer. New plugs get a backfill as far back as they keep data."""
from __future__ import annotations

import logging
from datetime import date, datetime

import psycopg
from psycopg_pool import ConnectionPool
from tapo import DiscoveryResult

from . import history
from .history import EnergyTarget, utcnow
from .plugs import PlugPool

log = logging.getLogger("tiris.collector")


# --------------------------------------------------------------------------- repository

def known_parents(con: psycopg.Connection) -> dict[str, tuple[str | None, str | None]]:
    rows = con.execute("SELECT device_id, ip, nickname FROM devices WHERE parent_id IS NULL AND NOT retired")
    return {r[0]: (r[1], r[2]) for r in rows.fetchall()}


def first_nonzero(con: psycopg.Connection) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for kind, table, col in (("hourly", "energy_hourly", "ts"), ("daily", "energy_daily", "day"),
                             ("monthly", "energy_monthly", "month")):
        for did, first in con.execute(f"SELECT device_id, MIN({col}) FROM {table} WHERE wh > 0 GROUP BY 1"):
            out.setdefault(did, {})[kind] = first
    return out


def last_5min(con: psycopg.Connection) -> dict[str, datetime]:
    return dict(con.execute("SELECT device_id, MAX(ts) FROM power_5min GROUP BY 1").fetchall())


def upsert_device(con: psycopg.Connection, t: EnergyTarget, tz_name: str | None, seen: datetime) -> None:
    # Only plug-owned fields are updated; room, category, note, protected stay as the user set them.
    con.execute(
        """
        INSERT INTO devices (device_id, parent_id, position, nickname, model, ip, mac, fw_ver, hw_ver, timezone,
                             first_seen, last_seen)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (device_id) DO UPDATE SET
            parent_id = excluded.parent_id, position = excluded.position, nickname = excluded.nickname,
            model = excluded.model, ip = excluded.ip, mac = excluded.mac, fw_ver = excluded.fw_ver,
            hw_ver = excluded.hw_ver, timezone = COALESCE(excluded.timezone, devices.timezone),
            last_seen = excluded.last_seen
        """,
        (t.device_id, t.parent_id, t.position, t.nickname, t.model, t.ip, t.mac, t.fw_ver, t.hw_ver, tz_name,
         seen, seen),
    )


def upsert_hourly(con, device_id: str, rows: list[tuple[datetime, int]], now: datetime) -> None:
    if rows:
        con.cursor().executemany(
            """INSERT INTO energy_hourly (device_id, ts, wh, updated_at) VALUES (%s, %s, %s, %s)
               ON CONFLICT (device_id, ts) DO UPDATE SET wh = GREATEST(energy_hourly.wh, excluded.wh),
               updated_at = excluded.updated_at""",
            [(device_id, ts, wh, now) for ts, wh in rows])


def upsert_period(con, table: str, col: str, device_id: str, rows: list[tuple[date, int]], now: datetime) -> None:
    assert (table, col) in (("energy_daily", "day"), ("energy_monthly", "month"))
    if rows:
        con.cursor().executemany(
            f"""INSERT INTO {table} (device_id, {col}, wh, updated_at) VALUES (%s, %s, %s, %s)
                ON CONFLICT (device_id, {col}) DO UPDATE SET wh = GREATEST({table}.wh, excluded.wh),
                updated_at = excluded.updated_at""",
            [(device_id, d, wh, now) for d, wh in rows])


def upsert_5min(con, device_id: str, rows: list[tuple[datetime, int]], now: datetime) -> None:
    if rows:  # the current interval still changes -> overwrite
        con.cursor().executemany(
            """INSERT INTO power_5min (device_id, ts, w, updated_at) VALUES (%s, %s, %s, %s)
               ON CONFLICT (device_id, ts) DO UPDATE SET w = excluded.w, updated_at = excluded.updated_at""",
            [(device_id, ts, w, now) for ts, w in rows])


# --------------------------------------------------------------------------- run

async def collect(db: ConnectionPool, plugs: PlugPool, force_backfill: bool = False) -> dict:
    """One collection run. Returns {status, ok, failed, errors, warnings}."""
    started = utcnow()
    with db.connection() as con:
        run_id = con.execute("INSERT INTO runs (started_at) VALUES (%s) RETURNING id", (started,)).fetchone()[0]
        known = known_parents(con)
        firsts = first_nonzero(con)
        last5 = last_5min(con)

    outcome = await plugs.discover(known)
    warnings = list(outcome.errors)
    errors: list[str] = []
    for did, (ip, nick) in known.items():
        if did not in outcome.parents:
            errors.append(f"Known plug not reachable: {nick or did} (last seen at {ip})")

    # Share one session per plug: hand the freshly logged-in handlers to the pool before anything else
    # uses them, so the live poller does not log in again and evict the collector's session.
    for res in outcome.parents.values():
        plugs.adopt(res.address[0], res.handler)

    targets: list[EnergyTarget] = []
    for res in outcome.parents.values():
        try:
            targets += await history.expand_targets(res)
        except Exception as exc:
            errors.append(f"{res.nickname}: sockets not readable: {exc}")
        if isinstance(res, DiscoveryResult.PowerStripEnergyMonitoring):
            with db.connection() as con:
                upsert_device(con, history.parent_as_device_row(res), None, utcnow())

    ok = failed = 0
    for t in targets:
        backfill = force_backfill or t.device_id not in firsts
        try:
            data = await history.fetch_with_retry(t, backfill, firsts.get(t.device_id))
        except Exception as exc:
            failed += 1
            hint = " (check the Tapo password; not retried to avoid a lockout)" if history.is_auth_error(exc) else ""
            errors.append(f"{t.label}: {exc}{hint}")
            continue
        errors += data.warnings
        warnings += data.notes
        now = utcnow()
        try:
            with db.connection() as con:
                upsert_device(con, t, data.tz.key, now)
                upsert_hourly(con, t.device_id, data.hourly, now)
                upsert_period(con, "energy_daily", "day", t.device_id, data.daily, now)
                upsert_period(con, "energy_monthly", "month", t.device_id, data.monthly, now)
            ok += 1
            log.info("%s: %d hours, %d days, %d months%s", t.label, len(data.hourly), len(data.daily),
                     len(data.monthly), " [backfill]" if backfill else "")
        except Exception as exc:
            failed += 1
            errors.append(f"{t.label}: database error: {exc}")
            continue
        try:  # extra detail; must not fail the run
            p5 = await history.fetch_power_5min(t.handler, last5.get(t.device_id))
            with db.connection() as con:
                upsert_5min(con, t.device_id, p5, utcnow())
        except Exception as exc:
            warnings.append(f"{t.label}: 5-minute values not read: {exc}")

    failed += sum(1 for e in errors if e.startswith("Known plug") or "sockets not readable" in e)
    if ok == 0 and not errors:
        errors.append("No energy monitoring plugs found. Check the discovery targets.")
    status = "ok" if not errors else ("partial" if ok else "failed")
    for w in warnings:
        log.warning(w)
    for e in errors:
        log.error(e)
    message = "\n".join(errors + [f"WARN: {w}" for w in warnings])[:4000]
    with db.connection() as con:
        con.execute("UPDATE runs SET finished_at = %s, status = %s, devices_ok = %s, devices_failed = %s, "
                    "message = %s WHERE id = %s", (utcnow(), status, ok, failed, message, run_id))
    log.info("collection finished: status=%s ok=%d failed=%d", status, ok, failed)
    return {"status": status, "ok": ok, "failed": failed, "errors": errors, "warnings": warnings}
