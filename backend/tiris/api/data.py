"""Read API: overview, time series from the aggregates, collector runs."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from .. import collector
from ..config import settings
from ..db import pool
from ..overview import overview
from ..state import state

router = APIRouter(prefix="/api")

BUCKETS = {"1m": ("power_1m", 60), "15m": ("power_15m", 900), "1h": ("power_1h", 3600)}


@router.get("/health")
def health():
    with pool().connection() as con:
        con.execute("SELECT 1")
    return {"ok": True, "tapo": bool(state.plugs and state.plugs.enabled), "live": state.live is not None}


@router.get("/overview")
def get_overview(days: int = Query(30, ge=7, le=3650), device: str | None = None):
    return overview(days=days, device=device, price=current_price())


def current_price() -> float | None:
    """Gross price per kWh of the first electricity meter's tariff today, if any."""
    from ..costs import Tariff, Tariffs
    today = datetime.now(settings().tz).date()
    with pool().connection() as con:
        rows = con.execute(
            """SELECT t.valid_from, t.valid_to, t.energy_ct_net, t.base_eur_year_net, t.vat_pct, t.contract_end
               FROM tariffs t JOIN meters m ON m.id = t.meter_id
               WHERE m.kind = 'electricity' AND NOT m.archived
                 AND m.id = (SELECT MIN(id) FROM meters WHERE kind = 'electricity' AND NOT archived)""").fetchall()
    ts = Tariffs([Tariff(r[0], r[1], float(r[2]), float(r[3]), float(r[4]), r[5]) for r in rows])
    return ts.eur_kwh(today)


@router.get("/series")
def series(
    start: datetime = Query(..., alias="from"),
    end: datetime | None = Query(None, alias="to"),
    bucket: str = Query("auto", pattern="^(auto|1m|15m|1h)$"),
    device: list[str] | None = Query(None),
    split: bool = False,
):
    """Power and energy over time from the continuous aggregates. `auto` keeps the point count near 300-1500.
    Without `split` the devices are summed per bucket."""
    end = end or datetime.now(settings().tz)
    if end <= start:
        raise HTTPException(422, "'to' must be after 'from'")
    span = (end - start).total_seconds()
    if bucket == "auto":
        bucket = "1m" if span <= 36 * 3600 else "15m" if span <= 15 * 86400 else "1h"
    view, step = BUCKETS[bucket]
    if span / step > 20000:
        raise HTTPException(422, "range too large for this bucket")
    with pool().connection() as con:
        rows = con.execute(
            f"""SELECT bucket, device_id, w_avg, w_min, w_max, v_avg, wh, n FROM {view}
                WHERE bucket >= %s AND bucket < %s AND (%s::text[] IS NULL OR device_id = ANY(%s))
                ORDER BY bucket""",
            (start, end, device, device)).fetchall()
    if split:
        out: dict[str, list] = {}
        for b, did, w, wmin, wmax, v, wh, n in rows:
            out.setdefault(did, []).append([b.timestamp(), w, wmin, wmax, v, wh, n])
        return {"bucket": bucket, "step_s": step, "series": out}
    agg: dict[datetime, list] = {}
    for b, _did, w, wmin, wmax, v, wh, n in rows:
        a = agg.setdefault(b, [0.0, 0.0, 0.0, [], 0.0, 0])
        a[0] += w or 0
        a[1] += wmin or 0
        a[2] += wmax or 0
        if v:
            a[3].append(v)
        a[4] += wh or 0
        a[5] += n or 0
    points = [[b.timestamp(), round(a[0], 2), round(a[1], 2), round(a[2], 2),
               round(sum(a[3]) / len(a[3]), 1) if a[3] else None, round(a[4], 3), a[5]]
              for b, a in sorted(agg.items())]
    return {"bucket": bucket, "step_s": step, "columns": ["t", "w", "w_min", "w_max", "v", "wh", "n"],
            "points": points}


@router.get("/runs")
def runs(limit: int = Query(20, ge=1, le=200)):
    with pool().connection() as con:
        rows = con.execute("SELECT id, started_at, finished_at, status, devices_ok, devices_failed, message "
                           "FROM runs ORDER BY id DESC LIMIT %s", (limit,)).fetchall()
    return [{"id": r[0], "started_at": r[1].isoformat(), "finished_at": r[2].isoformat() if r[2] else None,
             "status": r[3], "ok": r[4], "failed": r[5], "message": r[6]} for r in rows]


@router.post("/collect")
async def collect_now(backfill: bool = False):
    if state.plugs is None or not state.plugs.enabled:
        raise HTTPException(503, "no Tapo account configured")
    if state.collecting:
        raise HTTPException(409, "a collection is already running")
    state.collecting = True
    try:
        return await collector.collect(pool(), state.plugs, force_backfill=backfill)
    finally:
        state.collecting = False
        if state.live:
            state.live.reload_devices()


async def scheduler() -> None:
    """Collect every `collect_interval_min`, aligned to the clock; catch up at start if the last run is old."""
    s = settings()
    every = timedelta(minutes=s.collect_interval_min)
    with pool().connection() as con:
        last = con.execute("SELECT MAX(finished_at) FROM runs").fetchone()[0]
    if last is None or datetime.now(last.tzinfo) - last >= every:
        await _guarded_collect()
    while True:
        now = datetime.now(s.tz)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        n = int((now - midnight) / every) + 1
        nxt = midnight + n * every
        await asyncio.sleep(max(1.0, (nxt - now).total_seconds()))
        await _guarded_collect()


async def _guarded_collect() -> None:
    if state.collecting or state.plugs is None or not state.plugs.enabled:
        return
    state.collecting = True
    try:
        await collector.collect(pool(), state.plugs)
    except Exception:
        logging.getLogger("tiris.scheduler").exception("collection failed")
    finally:
        state.collecting = False
        if state.live:
            state.live.reload_devices()
