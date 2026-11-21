"""Overview: KPIs, daily series, months, load profile and devices, from the device history tables.

Ported from an earlier prototype. Energy in Wh, power in W.
"""
from __future__ import annotations

import statistics
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import HTTPException, Query

from .config import settings
from .db import pool

COLOR_SLOTS = 6          # the top 6 devices get their own colour, the rest is "other"


def slot_for_rank(i: int) -> int:
    return i + 1 if i < COLOR_SLOTS else 0


def color_slots(con) -> dict[str, int]:
    """Colour slot per device, the same ranking as the overview (energy of the last 90 days)."""
    rows = con.execute(
        """SELECT d.device_id FROM devices d
           WHERE NOT d.retired AND NOT EXISTS (SELECT 1 FROM devices c WHERE c.parent_id = d.device_id)
           ORDER BY COALESCE((SELECT SUM(wh) FROM energy_daily x WHERE x.device_id = d.device_id
                              AND x.day >= CURRENT_DATE - 90), 0) DESC, COALESCE(d.nickname, d.device_id)""").fetchall()
    return {r[0]: slot_for_rank(i) for i, r in enumerate(rows)}


def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


def overview(days: int = Query(30, ge=7, le=3650), device: str | None = None, price: float | None = None):
    now = datetime.now(settings().tz)
    today = now.date()
    with pool().connection() as con:
        devs = con.execute(
            """
            SELECT d.device_id, COALESCE(d.nickname, d.device_id), d.model, d.ip, d.last_seen,
                   COALESCE((SELECT SUM(wh) FROM energy_daily x WHERE x.device_id = d.device_id
                             AND x.day >= CURRENT_DATE - 90), 0) AS total
            FROM devices d
            WHERE NOT d.retired AND NOT EXISTS (SELECT 1 FROM devices c WHERE c.parent_id = d.device_id)
            ORDER BY total DESC, 2
            """
        ).fetchall()
        if not devs:
            raise HTTPException(503, "no data yet; is the collector running?")
        # Colour follows the device (rank by the last 90 days), never the current filter or range
        devices = [{"id": r[0], "name": r[1].strip(), "model": r[2], "ip": r[3],
                    "last_seen": r[4].isoformat() if r[4] else None,
                    "slot": slot_for_rank(i)} for i, r in enumerate(devs)]
        ids = [d["id"] for d in devices]
        if device and device not in ids:
            raise HTTPException(404, "unknown device")
        sel = [device] if device else ids

        # ---- daily values (all devices, for sparklines and ranking; the selection for charts)
        first_day = today - timedelta(days=max(days, 62) + 7)
        daily = defaultdict(dict)  # device -> {day: wh}
        for did, day, wh in con.execute(
                "SELECT device_id, day, wh FROM energy_daily WHERE day >= %s AND day <= %s", (first_day, today)):
            daily[did][day] = wh
        oldest = con.execute("SELECT MIN(day) FROM energy_daily WHERE wh > 0").fetchone()[0]

        # ---- hourly values (last 35 days), local time
        hourly = defaultdict(lambda: defaultdict(int))  # device -> {local_dt: wh}
        for did, ts, wh in con.execute(
                "SELECT device_id, ts, wh FROM energy_hourly WHERE ts >= now() - INTERVAL '35 days'"):
            hourly[did][ts.astimezone(settings().tz)] += wh

        monthly = defaultdict(dict)
        m_start = (today.replace(day=1) - timedelta(days=370)).replace(day=1)
        for did, month, wh in con.execute(
                "SELECT device_id, month, wh FROM energy_monthly WHERE month >= %s", (m_start,)):
            monthly[did][month] = wh

        last_run = con.execute(
            "SELECT finished_at, status FROM runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
        last_ok = con.execute(
            "SELECT MAX(finished_at) FROM runs WHERE status IN ('ok', 'partial')").fetchone()[0]

    def day_sum(day: date, who=sel) -> int:
        return sum(daily[d].get(day, 0) for d in who)

    def span(a: date, b: date, who=sel) -> int:  # inklusive
        return sum(day_sum(a + timedelta(days=i), who) for i in range((b - a).days + 1))

    def hourly_totals(who) -> dict[datetime, int]:
        tot: dict[datetime, int] = defaultdict(int)
        for d in who:
            for ts, wh in hourly[d].items():
                tot[ts] += wh
        return tot

    def base_load_w(who) -> float | None:
        """Base load: the weakest hour of each complete day, median of the last 7 days (Wh per h = W)."""
        tot = hourly_totals(who)
        per_day: dict[date, list[int]] = defaultdict(list)
        for ts, wh in tot.items():
            per_day[ts.date()].append(wh)
        mins = [min(v) for dd, v in per_day.items() if today - timedelta(days=7) <= dd < today and len(v) >= 20]
        return median(mins)

    yesterday = today - timedelta(days=1)

    # ---- KPIs
    tot_h = hourly_totals(sel)
    now_hour = max((ts for ts in tot_h if ts.date() == today), default=None)
    today_wh = day_sum(today)
    if now_hour is not None:
        today_h = sum(wh for ts, wh in tot_h.items() if ts.date() == today)
        yday_same = sum(wh for ts, wh in tot_h.items() if ts.date() == yesterday and ts.hour <= now_hour.hour)
        today_wh = max(today_wh, today_h)
    else:
        yday_same = None

    last7 = span(today - timedelta(days=7), yesterday)
    prev7 = span(today - timedelta(days=14), today - timedelta(days=8))
    last30 = span(today - timedelta(days=30), yesterday)
    avg14 = span(today - timedelta(days=14), yesterday) / 14

    month_start = today.replace(day=1)
    dim = monthrange(today.year, today.month)[1]
    mtd_complete = span(month_start, yesterday) if today.day > 1 else 0
    mtd = mtd_complete + day_sum(today)
    forecast_month = mtd_complete + avg14 * (dim - (today.day - 1))
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    prev_same = span(prev_month_start, prev_month_start + timedelta(days=today.day - 2)) if today.day > 1 else None
    prev_month_total = sum(monthly[d].get(prev_month_start, 0) for d in sel)

    base_w = base_load_w(sel)

    # ---- daily series for the chart: top devices on their own, the rest as "other"
    range_start = max(today - timedelta(days=days - 1), oldest or today)
    keys = [d["id"] for d in devices if d["slot"] and d["id"] in sel]
    rest = [d for d in sel if d not in keys]
    series = []
    for i in range((today - range_start).days + 1):
        dd = range_start + timedelta(days=i)
        row = {"day": dd.isoformat(), "by": {k: daily[k].get(dd, 0) for k in keys}}
        if rest:
            row["by"]["other"] = day_sum(dd, rest)
        row["total"] = sum(row["by"].values())
        series.append(row)

    # ---- months (13 including the current one)
    months = []
    m = month_start
    for _ in range(13):
        months.append({"month": m.isoformat(), "wh": sum(monthly[d].get(m, 0) for d in sel),
                       "partial": m == month_start})
        m = (m - timedelta(days=1)).replace(day=1)
    months.reverse()
    while months and months[0]["wh"] == 0:
        months.pop(0)

    # ---- load profile: mean Wh per weekday x hour (all hours of the last 35 days)
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for ts, wh in tot_h.items():
        if ts.date() < today:
            cells[(ts.isoweekday(), ts.hour)].append(wh)
    heat = [{"dow": k[0], "hour": k[1], "wh": round(sum(v) / len(v), 1), "n": len(v)} for k, v in cells.items()]
    hourly_days = len({ts.date() for ts in tot_h if ts.date() < today})

    # ---- devices
    rows = []
    for d in devices:
        did = d["id"]
        spark = [daily[did].get(today - timedelta(days=29 - i), 0) for i in range(30)]
        rows.append({
            **d,
            "range_wh": span(range_start, today, [did]),
            "last30_wh": span(today - timedelta(days=30), yesterday, [did]),
            "mtd_wh": span(month_start, today, [did]),
            "today_wh": day_sum(today, [did]),
            "spark": spark,
            "base_w": base_load_w([did]),
        })

    return {
        "now": now.isoformat(),
        "price": price,
        "last_run": {"at": last_run[0].isoformat(), "status": last_run[1]} if last_run else None,
        "last_ok": last_ok.isoformat() if last_ok else None,
        "selected": device,
        "range": {"start": range_start.isoformat(), "end": today.isoformat(), "days": len(series)},
        "kpi": {
            "today_wh": today_wh,
            "yesterday_same_time_wh": yday_same,
            "now_hour": now_hour.isoformat() if now_hour else None,
            "yesterday_wh": day_sum(yesterday),
            "last7_wh": last7, "prev7_wh": prev7,
            "last30_wh": last30,
            "mtd_wh": mtd, "mtd_complete_wh": mtd_complete, "prev_month_same_wh": prev_same,
            "prev_month_wh": prev_month_total,
            "forecast_month_wh": round(forecast_month),
            "forecast_year_wh": round(last30 / 30 * 365),
            "base_w": base_w,
            "days_in_month": dim,
            "range_wh": sum(r["total"] for r in series),
            "peak_day": max(series, key=lambda r: r["total"]) if series else None,
        },
        "daily": series,
        "series_keys": keys + (["other"] if rest else []),
        "months": months,
        "heat": heat,
        "heat_days": hourly_days,
        "devices": rows,
    }


