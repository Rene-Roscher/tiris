"""Costs per meter: tariffs with validity, readings, installment plans, payments, and a forecast of the billing year.

Electricity meters are coupled to the plugs: house = plugs (measured) + unmetered rest per day. The rest is
additive, calibrated on the latest meter interval with complete plug data; on real data it matched the meter
over several months, where a proportional model mis-scaled a device used only in summer. The tariff maths
was checked against a real yearly bill and matched it to the cent.
Gas meters have no plugs: consumption comes from readings, converted with calorific value and z-number.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta

import psycopg


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def month_start(d: date) -> date:
    return d.replace(day=1)


@dataclass
class Tariff:
    valid_from: date
    valid_to: date | None
    energy_ct_net: float
    base_eur_year_net: float
    vat_pct: float
    contract_end: date | None

    @property
    def eur_kwh(self) -> float:
        return self.energy_ct_net * (1 + self.vat_pct / 100) / 100

    @property
    def base_eur_day(self) -> float:
        return self.base_eur_year_net * (1 + self.vat_pct / 100) / 365


class Tariffs:
    def __init__(self, rows: list[Tariff]):
        self.rows = sorted(rows, key=lambda t: t.valid_from)

    def at(self, d: date) -> Tariff | None:
        """Tariff valid on d; after the last tariff ends, the last one is assumed (flagged by the caller)."""
        cur = None
        for t in self.rows:
            if t.valid_from <= d and (t.valid_to is None or d <= t.valid_to):
                cur = t
        if cur is None and self.rows:
            past = [t for t in self.rows if t.valid_from <= d]
            cur = past[-1] if past else self.rows[0]
        return cur

    def eur_kwh(self, d: date) -> float | None:
        t = self.at(d)
        return t.eur_kwh if t else None

    def base_eur_day(self, d: date) -> float:
        t = self.at(d)
        return t.base_eur_day if t else 0.0

    def covered(self, d: date) -> bool:
        return any(t.valid_from <= d and (t.valid_to is None or d <= t.valid_to) for t in self.rows)


def load_meter(con: psycopg.Connection, meter_id: int) -> dict:
    m = con.execute("SELECT id, kind, name, number, unit, calorific_value, z_number, archived FROM meters "
                    "WHERE id = %s", (meter_id,)).fetchone()
    if not m:
        raise KeyError(meter_id)
    tariffs = [Tariff(r[0], r[1], float(r[2]), float(r[3]), float(r[4]), r[5]) for r in con.execute(
        "SELECT valid_from, valid_to, energy_ct_net, base_eur_year_net, vat_pct, contract_end FROM tariffs "
        "WHERE meter_id = %s ORDER BY valid_from", (meter_id,))]
    tariff_rows = con.execute(
        "SELECT id, valid_from, valid_to, provider, name, energy_ct_net, base_eur_year_net, vat_pct, contract_end "
        "FROM tariffs WHERE meter_id = %s ORDER BY valid_from", (meter_id,)).fetchall()
    readings = con.execute("SELECT day, value, estimated, note FROM meter_readings WHERE meter_id = %s ORDER BY day",
                           (meter_id,)).fetchall()
    plans = con.execute("SELECT id, valid_from, valid_to, amount_gross, note FROM installment_plans "
                        "WHERE meter_id = %s ORDER BY valid_from", (meter_id,)).fetchall()
    payments = con.execute("SELECT id, day, amount, kind, note, external_ref FROM payments WHERE meter_id = %s "
                           "ORDER BY day DESC, id", (meter_id,)).fetchall()
    factor = 1.0
    if m[1] == "gas" and m[4] == "m3":
        factor = float(m[5] or 0) * float(m[6] or 0) or 0.0
    return {
        "meter": {"id": m[0], "kind": m[1], "name": m[2], "number": m[3], "unit": m[4],
                  "calorific_value": float(m[5]) if m[5] is not None else None,
                  "z_number": float(m[6]) if m[6] is not None else None, "archived": m[7],
                  "kwh_per_unit": factor if m[4] == "m3" else 1.0},
        "tariffs": Tariffs(tariffs), "tariff_rows": tariff_rows, "readings": readings, "plans": plans,
        "payments": payments,
    }


def due_dates(plans: list[tuple], start: date, end: date) -> list[tuple[date, float]]:
    """Monthly due dates of all plans inside [start, end]."""
    out = []
    for _, vf, vt, amount, _ in plans:
        d, i = vf, 0
        while d <= end and (vt is None or d <= vt):
            if d >= start:
                out.append((d, float(amount)))
            i += 1
            d = add_months(vf, i)
    return sorted(out)


def compute(con: psycopg.Connection, meter_id: int, today: date, plugs: dict | None = None) -> dict:
    """plugs (electricity only): {daily: {date: wh} for complete days, monthly: {month: wh}, complete_from: date,
    last30_wh: int, devices: [{id, name, last30_wh, base_w, ...}]}."""
    d = load_meter(con, meter_id)
    meter, tariffs, readings = d["meter"], d["tariffs"], d["readings"]
    to_kwh = meter["kwh_per_unit"] or 1.0
    price = tariffs.eur_kwh(today)
    cur = tariffs.at(today)
    out: dict = {
        "meter": meter,
        "tariffs": [{"id": r[0], "valid_from": r[1].isoformat(), "valid_to": r[2].isoformat() if r[2] else None,
                     "provider": r[3], "name": r[4], "energy_ct_net": float(r[5]), "base_eur_year_net": float(r[6]),
                     "vat_pct": float(r[7]), "contract_end": r[8].isoformat() if r[8] else None,
                     "energy_ct_gross": round(float(r[5]) * (1 + float(r[7]) / 100), 4),
                     "base_eur_month_gross": round(float(r[6]) * (1 + float(r[7]) / 100) / 12, 2)}
                    for r in d["tariff_rows"]],
        "readings": [{"day": r[0].isoformat(), "value": float(r[1]), "estimated": r[2], "note": r[3]}
                     for r in readings],
        "plans": [{"id": p[0], "valid_from": p[1].isoformat(), "valid_to": p[2].isoformat() if p[2] else None,
                   "amount_gross": float(p[3]), "note": p[4]} for p in d["plans"]],
        "payments": [{"id": p[0], "day": p[1].isoformat(), "amount": float(p[2]), "kind": p[3], "note": p[4],
                      "external_ref": p[5]} for p in d["payments"]],
        "price_eur_kwh": price,
        "base_eur_month": round(tariffs.base_eur_day(today) * 365 / 12, 2) if cur else None,
        "contract_end": cur.contract_end.isoformat() if cur and cur.contract_end else None,
        "warnings": [],
    }
    if meter["unit"] == "m3" and not meter["kwh_per_unit"]:
        out["warnings"].append("gas_conversion_missing")

    pd = plugs or {}
    pdaily: dict[date, int] = pd.get("daily", {})
    pmonthly: dict[date, int] = pd.get("monthly", {})
    complete_from: date | None = pd.get("complete_from")

    def plugs_wh(a: date, b: date) -> tuple[float, bool]:
        """Plug energy a..b inclusive: daily values where complete, else the month value pro rata."""
        if not plugs:
            return 0.0, False
        total, exact = 0.0, True
        m = month_start(a)
        while m <= b:
            dim = monthrange(m.year, m.month)[1]
            lo, hi = max(a, m), min(b, m.replace(day=dim))
            span = [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]
            if all(x in pdaily for x in span):
                total += sum(pdaily[x] for x in span)
            elif complete_from and m >= complete_from and pmonthly.get(m):
                elapsed = (min(today, m.replace(day=dim)) - m).days + 1
                total += pmonthly[m] * len(span) / max(1, elapsed)
                exact = False
            else:
                return 0.0, False
            m = add_months(m, 1)
        return total, exact

    # ---- meter intervals
    intervals = []
    for (d0, v0, *_), (d1, v1, est1, _) in zip(readings, readings[1:], strict=False):
        days = (d1 - d0).days
        if days <= 0:
            continue
        kwh = (float(v1) - float(v0)) * to_kwh
        p_wh, exact = plugs_wh(d0 + timedelta(days=1), d1)
        intervals.append({"from": d0.isoformat(), "to": d1.isoformat(), "days": days, "kwh": round(kwh, 1),
                          "kwh_day": round(kwh / days, 2), "estimated": bool(est1),
                          "plugs_kwh": round(p_wh / 1000, 1) if p_wh else None,
                          "coverage": round(p_wh / 1000 / kwh, 3) if p_wh and kwh > 0 else None,
                          "plugs_exact": exact})
    out["intervals"] = intervals
    cal = next((iv for iv in reversed(intervals) if iv["coverage"]), None)

    # ---- consumption per day now
    meter_day = intervals[-1]["kwh_day"] if intervals else None
    rest_day = max(0.0, (cal["kwh"] - cal["plugs_kwh"]) / cal["days"]) if cal else None
    plugs_day = pd.get("last30_wh", 0) / 1000 / 30 if plugs else None
    if plugs and rest_day is not None:
        house_day = plugs_day + rest_day
    else:
        house_day = meter_day
    out |= {"plugs_kwh_day": round(plugs_day, 2) if plugs_day is not None else None,
            "rest_kwh_day": round(rest_day, 2) if rest_day is not None else None,
            "house_kwh_day": round(house_day, 2) if house_day else None,
            "house_kwh_year": round(house_day * 365) if house_day else None,
            "plugs_share": round(plugs_day / house_day, 3) if plugs_day and house_day else None,
            "calibration": cal}

    # ---- billing year: from the day after the latest real reading
    real = [r for r in readings if not r[2]]
    if real and house_day and price is not None:
        start = real[-1][0] + timedelta(days=1)
        end = add_months(start, 12) - timedelta(days=1)
        known_until, known_kwh = real[-1][0], 0.0
        if readings[-1][0] > real[-1][0]:
            known_until, known_kwh = readings[-1][0], (float(readings[-1][1]) - float(real[-1][1])) * to_kwh
        so_far_end = min(today - timedelta(days=1), end)
        est_kwh, measured = known_kwh, known_until > real[-1][0]
        if so_far_end > known_until:
            n = (so_far_end - known_until).days
            p_wh, _ = plugs_wh(known_until + timedelta(days=1), so_far_end)
            if p_wh and rest_day is not None:
                est_kwh += p_wh / 1000 + rest_day * n
            else:
                est_kwh += house_day * n
        remaining = max(0, (end - so_far_end).days)
        total_kwh = est_kwh + house_day * remaining

        cost, day = 0.0, start
        per_day_so_far = est_kwh / max(1, (so_far_end - start).days + 1)
        assumed = False
        while day <= end:
            kwh_d = per_day_so_far if day <= so_far_end else house_day
            cost += kwh_d * tariffs.eur_kwh(day) + tariffs.base_eur_day(day)
            assumed = assumed or not tariffs.covered(day)
            day += timedelta(days=1)

        due = due_dates(d["plans"], start, end + timedelta(days=45))
        planned = sum(a for _, a in due)
        paid = sum(a for dd, a in due if dd <= today)
        booked = [(p[1], float(p[2])) for p in d["payments"]
                  if p[3] == "installment" and start <= p[1] <= end + timedelta(days=45)]
        source = "plan"
        if booked:
            paid = sum(a for dd, a in booked if dd <= today)
            last = max(dd for dd, _ in booked)
            planned = paid + sum(a for dd, a in due if dd > max(today, last))
            source = "payments"
        out["billing"] = {
            "start": start.isoformat(), "end": end.isoformat(),
            "elapsed_days": (so_far_end - start).days + 1, "total_days": (end - start).days + 1,
            "kwh_so_far": round(est_kwh), "kwh_so_far_measured": measured and so_far_end <= known_until,
            "kwh_forecast": round(total_kwh), "cost_forecast": round(cost, 2),
            "installments_total": round(planned, 2), "installments_paid": round(paid, 2),
            "installments_count": len(due), "paid_source": source,
            "balance": round(cost - planned, 2),               # > 0 back payment, < 0 refund
            "fair_installment": round(cost / len(due), 2) if due else None,
            "tariff_assumed": assumed,
        }

    # ---- months (electricity with plugs): measured plugs + rest + base price
    if plugs and price is not None:
        months = []
        m = add_months(month_start(today), -12)
        while m <= month_start(today):
            wh = pmonthly.get(m, 0)
            p = tariffs.eur_kwh(m)
            dim = monthrange(m.year, m.month)[1]
            days_m = today.day if m == month_start(today) else dim
            complete = complete_from is not None and m >= complete_from
            rest = rest_day * days_m if complete and rest_day is not None else None
            base = tariffs.base_eur_day(m) * days_m
            months.append({"month": m.isoformat(), "plugs_kwh": round(wh / 1000, 1),
                           "plugs_eur": round(wh / 1000 * p, 2),
                           "rest_kwh": round(rest, 1) if rest is not None else None,
                           "rest_eur": round(rest * p, 2) if rest is not None else None,
                           "base_eur": round(base, 2), "complete": complete,
                           "partial": m == month_start(today)})
            m = add_months(m, 1)
        out["months"] = [x for x in months if x["plugs_kwh"] > 0]

        devs = []
        for r in pd.get("devices", []):
            kwh_year = r["last30_wh"] / 1000 / 30 * 365
            standby_kwh = (r.get("base_w") or 0) * 8.76
            devs.append({"id": r["id"], "name": r["name"], "kwh_year": round(kwh_year, 1),
                         "eur_year": round(kwh_year * price, 2), "eur_month": round(kwh_year * price / 12, 2),
                         "standby_w": r.get("base_w"), "standby_eur_year": round(standby_kwh * price, 2)})
        out["devices"] = sorted(devs, key=lambda x: -x["eur_year"])
    return out


def payments_by_year(con: psycopg.Connection) -> list[dict]:
    rows = con.execute(
        """SELECT extract(year FROM p.day)::int, COALESCE(m.kind, 'unassigned'), SUM(p.amount), COUNT(*)
           FROM payments p LEFT JOIN meters m ON m.id = p.meter_id GROUP BY 1, 2 ORDER BY 1 DESC""").fetchall()
    years: dict[int, dict] = {}
    for y, kind, amount, _n in rows:
        e = years.setdefault(y, {"year": y, "total": 0.0})
        e[kind] = round(float(amount), 2)
        e["total"] = round(e["total"] + float(amount), 2)
    return list(years.values())
