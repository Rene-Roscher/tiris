"""Per-device analysis: power, voltage, on/off cycles, daily energy.

Cycles are detected on the power curve with hysteresis: "on" above `on_w`, "off" below `off_w` (half of it), so a
compressor that wobbles around the threshold counts once. Up to 2 days the raw samples (~2 s) are used, beyond
that the minute aggregate, which cannot see cycles shorter than a minute.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Query

from .api.data import current_price
from .config import settings
from .db import pool

router = APIRouter(prefix="/api/devices")
RAW_MAX = timedelta(days=2)


def detect_cycles(points: list[tuple[float, float]], on_w: float) -> dict:
    """points: (unix ts, W) sorted. Returns cycle count, on-time share and durations (s)."""
    off_w = on_w / 2
    cycles, durations, on_time = 0, [], 0.0
    state, started, prev_t = False, None, None
    for t, w in points:
        if prev_t is not None and state and t - prev_t < 600:   # gaps > 10 min are not counted as "on"
            on_time += t - prev_t
        if not state and w >= on_w:
            state, started = True, t
            cycles += 1
        elif state and w < off_w:
            state = False
            if started is not None:
                durations.append(t - started)
        prev_t = t
    span = points[-1][0] - points[0][0] if len(points) > 1 else 0
    return {"count": cycles, "duty": on_time / span if span else None,
            "median_s": statistics.median(durations) if durations else None,
            "max_s": max(durations) if durations else None, "threshold_w": round(on_w, 1)}


@router.get("/{device_id}/analysis")
def analysis(device_id: str, hours: int = Query(24, ge=1, le=24 * 90)):
    end = datetime.now(settings().tz)
    start = end - timedelta(hours=hours)
    with pool().connection() as con:
        dev = con.execute("SELECT device_id, nickname, model, room, category, protected, first_seen FROM devices "
                          "WHERE device_id = %s", (device_id,)).fetchone()
        if not dev:
            raise HTTPException(404, "unknown device")
        use_raw = end - start <= RAW_MAX
        if use_raw:
            rows = con.execute("SELECT ts, w, v, a FROM power_samples WHERE device_id = %s AND ts >= %s ORDER BY ts",
                               (device_id, start)).fetchall()
            pts = [(r[0].timestamp(), float(r[1])) for r in rows]
            volts = [float(r[2]) for r in rows if r[2]]
            amps = [float(r[3]) for r in rows if r[3] is not None]
        else:
            rows = con.execute("SELECT bucket, w_avg, v_avg FROM power_1m WHERE device_id = %s AND bucket >= %s "
                               "ORDER BY bucket", (device_id, start)).fetchall()
            pts = [(r[0].timestamp(), float(r[1] or 0)) for r in rows]
            volts = [float(r[2]) for r in rows if r[2]]
            amps = []
            resolution = "1m"
            if len(rows) < hours * 60 * 0.8:
                # Live minutes cover too little of the range (tiris is new or was down): use the plug's own
                # 5-minute buffer (~10 days) for the power curve and the cycles instead.
                five = con.execute("SELECT ts, w FROM power_5min WHERE device_id = %s AND ts >= %s ORDER BY ts",
                                   (device_id, start)).fetchall()
                if len(five) > len(rows) / 5:
                    pts, resolution = [(r[0].timestamp(), float(r[1])) for r in five], "5min"
        # Energy from the plug's hourly history (authoritative), live minutes only for what it does not cover yet.
        wh_hourly, last_hour = con.execute(
            "SELECT COALESCE(SUM(wh), 0), MAX(ts) FROM energy_hourly "
            "WHERE device_id = %s AND ts >= date_trunc('hour', %s)",
            (device_id, start)).fetchone()
        wh_live = con.execute(
            "SELECT COALESCE(SUM(wh), 0) FROM power_1m WHERE device_id = %s AND bucket >= %s",
            (device_id, (last_hour + timedelta(hours=1)) if last_hour else start)).fetchone()[0]
        wh = float(wh_hourly) + float(wh_live)
        daily = con.execute("SELECT day, wh FROM energy_daily WHERE device_id = %s AND day >= %s ORDER BY day",
                            (device_id, (end - timedelta(days=60)).date())).fetchall()
        base = con.execute(
            """SELECT percentile_cont(0.1) WITHIN GROUP (ORDER BY w_avg) FROM power_1m
               WHERE device_id = %s AND bucket >= now() - interval '7 days'""", (device_id,)).fetchone()[0]
    ws = [w for _, w in pts]
    base_w = float(base or 0)
    # Threshold from the 95th percentile, not the maximum: a compressor's inrush spike (591 W measured on a fridge
    # that runs at ~75 W) would otherwise push the threshold above the normal running power.
    p95 = sorted(ws)[int(len(ws) * 0.95)] if ws else 0
    on_w = max(3.0, base_w * 1.6 + 2, p95 * 0.15)
    return {
        "device": {"id": dev[0], "name": dev[1], "model": dev[2], "room": dev[3], "category": dev[4],
                   "protected": dev[5], "first_seen": dev[6].isoformat() if dev[6] else None},
        "range": {"from": start.isoformat(), "to": end.isoformat(), "hours": hours,
                  "resolution": "raw" if use_raw else resolution, "points": len(pts)},
        "price": current_price(),
        "energy_wh": round(float(wh), 1),
        "power": {"avg": round(statistics.fmean(ws), 2) if ws else None, "max": max(ws) if ws else None,
                  "min": min(ws) if ws else None, "base": round(base_w, 2)},
        "voltage": {"avg": round(statistics.fmean(volts), 1) if volts else None,
                    "min": min(volts) if volts else None, "max": max(volts) if volts else None},
        "current": {"max": max(amps) if amps else None},
        "cycles": detect_cycles(pts, on_w) if len(pts) > 2 else None,
        "daily": [{"day": d.isoformat(), "wh": w} for d, w in daily],
    }
