"""When did which device run: runs per device for one day, from the minute aggregate.

A run is a stretch of minutes above the device's own threshold, with gaps of up to MERGE_GAP minutes bridged (a
fridge compressor that dips for a minute is one run). The threshold follows the analysis view: the base load of
the day (10th percentile) times 1.6 plus 2 W, at least 3 W, and at least 15 % of the day's 95th percentile so a
device that idles at 20 W and works at 1 kW is not "on" while idling.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, HTTPException, Query

from .api.data import current_price
from .config import settings
from .db import pool

router = APIRouter(prefix="/api")
MERGE_GAP = 3        # minutes
MIN_RUN = 2          # minutes; shorter blips are not listed


def threshold(ws: list[float]) -> float:
    s = sorted(ws)
    if not s:
        return 3.0
    base = s[int(len(s) * 0.1)]
    p95 = s[min(len(s) - 1, int(len(s) * 0.95))]
    return max(3.0, base * 1.6 + 2, p95 * 0.15)


def find_runs(points: list[tuple[float, float, float]], on_w: float) -> list[dict]:
    """points: (unix ts of the minute, W avg, Wh) sorted. Returns runs with start, end, Wh and peak W."""
    runs: list[dict] = []
    cur: dict | None = None
    for t, w, wh in points:
        if w >= on_w:
            if cur and t - cur["end"] <= MERGE_GAP * 60:
                cur["end"] = t + 60
                cur["wh"] += wh
                cur["peak_w"] = max(cur["peak_w"], w)
            else:
                cur = {"start": t, "end": t + 60, "wh": wh, "peak_w": w}
                runs.append(cur)
        elif cur and t - cur["end"] <= MERGE_GAP * 60:
            cur["wh"] += wh   # energy in a bridged dip belongs to the run
    return [r for r in runs if r["end"] - r["start"] >= MIN_RUN * 60]


@router.get("/events")
def events(day: date | None = Query(None)):
    tz = settings().tz
    day = day or datetime.now(tz).date()
    start = datetime.combine(day, time(0), tz)
    end = start + timedelta(days=1)
    with pool().connection() as con:
        devs = con.execute("""SELECT device_id, COALESCE(nickname, device_id) FROM devices d WHERE NOT retired
                              AND NOT EXISTS (SELECT 1 FROM devices c WHERE c.parent_id = d.device_id)""").fetchall()
        rows = con.execute("SELECT bucket, device_id, w_avg, wh FROM power_1m WHERE bucket >= %s AND bucket < %s "
                           "ORDER BY bucket", (start, end)).fetchall()
    if not devs:
        raise HTTPException(503, "no devices yet")
    by: dict[str, list[tuple[float, float, float]]] = {}
    for b, did, w, wh in rows:
        by.setdefault(did, []).append((b.timestamp(), float(w or 0), float(wh or 0)))
    price = current_price()
    out = []
    for did, name in devs:
        pts = by.get(did, [])
        if not pts:
            continue
        on_w = threshold([p[1] for p in pts])
        runs = find_runs(pts, on_w)
        drawing = find_runs(pts, 1.0)          # any consumption at all, for the faint track
        ws = sorted(p[1] for p in pts)
        out.append({
            "id": did, "name": name.strip(), "threshold_w": round(on_w, 1),
            "minutes": len(pts), "wh": round(sum(p[2] for p in pts), 1),
            "on_s": sum(r["end"] - r["start"] for r in runs),
            "base_w": round(ws[int(len(ws) * 0.1)], 1),
            "runs": [{"start": r["start"], "end": r["end"], "wh": round(r["wh"], 1), "peak_w": round(r["peak_w"], 1)}
                     for r in runs],
            "drawing": [[r["start"], r["end"]] for r in drawing],
        })
    out.sort(key=lambda d: -d["wh"])
    return {"day": day.isoformat(), "start": start.timestamp(), "end": end.timestamp(), "price": price,
            "covered_from": min((p[0] for v in by.values() for p in v), default=None), "devices": out}
