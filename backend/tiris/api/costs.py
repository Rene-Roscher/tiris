"""Costs API: meters with tariffs, readings, installment plans and payments; forecast per meter."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from .. import costs
from ..config import settings
from ..db import pool
from ..overview import overview

router = APIRouter(prefix="/api")


# --------------------------------------------------------------------------- meters

class MeterIn(BaseModel):
    kind: str = Field(pattern="^(electricity|gas)$")
    name: str = Field(min_length=1, max_length=80)
    number: str | None = Field(None, max_length=60)
    unit: str = Field("kWh", pattern="^(kWh|m3)$")
    calorific_value: float | None = Field(None, gt=0, lt=20)
    z_number: float | None = Field(None, gt=0, lt=2)
    archived: bool = False


@router.get("/meters")
def list_meters():
    with pool().connection() as con:
        rows = con.execute("SELECT id, kind, name, number, unit, calorific_value, z_number, archived FROM meters "
                           "ORDER BY archived, kind, id").fetchall()
    return [{"id": r[0], "kind": r[1], "name": r[2], "number": r[3], "unit": r[4],
             "calorific_value": float(r[5]) if r[5] is not None else None,
             "z_number": float(r[6]) if r[6] is not None else None, "archived": r[7]} for r in rows]


@router.post("/meters")
def create_meter(m: MeterIn):
    with pool().connection() as con:
        mid = con.execute("INSERT INTO meters (kind, name, number, unit, calorific_value, z_number, archived) "
                          "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                          (m.kind, m.name, m.number, m.unit, m.calorific_value, m.z_number, m.archived)).fetchone()[0]
    return {"id": mid}


@router.put("/meters/{meter_id}")
def update_meter(meter_id: int, m: MeterIn):
    with pool().connection() as con:
        cur = con.execute("UPDATE meters SET kind = %s, name = %s, number = %s, unit = %s, calorific_value = %s, "
                          "z_number = %s, archived = %s WHERE id = %s",
                          (m.kind, m.name, m.number, m.unit, m.calorific_value, m.z_number, m.archived, meter_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "unknown meter")
    return {"ok": True}


@router.delete("/meters/{meter_id}")
def delete_meter(meter_id: int):
    with pool().connection() as con:
        con.execute("DELETE FROM meters WHERE id = %s", (meter_id,))
    return {"ok": True}


def plug_inputs(today: date) -> dict:
    """Plug energy for the electricity forecast: complete days, months, and where monthly sums are complete."""
    ov = overview(days=30, device=None, price=None)
    with pool().connection() as con:
        n_dev = con.execute("SELECT COUNT(*) FROM devices WHERE NOT retired AND parent_id IS NULL").fetchone()[0]
        daily = {d: int(wh) for d, wh in con.execute(
            "SELECT day, SUM(wh) FROM energy_daily GROUP BY day HAVING COUNT(*) >= %s", (n_dev,))}
        monthly = {m: int(wh) for m, wh in con.execute("SELECT month, SUM(wh) FROM energy_monthly GROUP BY month")}
        complete_from = con.execute(
            "SELECT MAX(first) FROM (SELECT MIN(month) AS first FROM energy_monthly WHERE wh > 0 GROUP BY device_id) f"
        ).fetchone()[0]
    return {"daily": daily, "monthly": monthly, "complete_from": complete_from,
            "last30_wh": ov["kpi"]["last30_wh"], "devices": ov["devices"]}


@router.get("/meters/{meter_id}/costs")
def meter_costs(meter_id: int):
    today = datetime.now(settings().tz).date()
    with pool().connection() as con:
        kind = con.execute("SELECT kind FROM meters WHERE id = %s", (meter_id,)).fetchone()
        if not kind:
            raise HTTPException(404, "unknown meter")
    plugs = None
    if kind[0] == "electricity":
        try:
            plugs = plug_inputs(today)
        except HTTPException:
            plugs = None     # no plug data yet
    with pool().connection() as con:
        return costs.compute(con, meter_id, today, plugs)


# --------------------------------------------------------------------------- tariffs

class TariffIn(BaseModel):
    valid_from: date
    valid_to: date | None = None
    provider: str | None = Field(None, max_length=80)
    name: str | None = Field(None, max_length=80)
    energy_ct_net: float = Field(gt=0, lt=500)
    base_eur_year_net: float = Field(ge=0, lt=10000)
    vat_pct: float = Field(19, ge=0, le=50)
    contract_end: date | None = None

    @model_validator(mode="after")
    def _range(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to before valid_from")
        return self


@router.post("/meters/{meter_id}/tariffs")
def add_tariff(meter_id: int, t: TariffIn):
    with pool().connection() as con:
        tid = con.execute(
            """INSERT INTO tariffs (meter_id, valid_from, valid_to, provider, name, energy_ct_net, base_eur_year_net,
                                    vat_pct, contract_end) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (meter_id, valid_from) DO UPDATE SET valid_to = excluded.valid_to,
                 provider = excluded.provider, name = excluded.name, energy_ct_net = excluded.energy_ct_net,
                 base_eur_year_net = excluded.base_eur_year_net, vat_pct = excluded.vat_pct,
                 contract_end = excluded.contract_end RETURNING id""",
            (meter_id, t.valid_from, t.valid_to, t.provider, t.name, t.energy_ct_net, t.base_eur_year_net,
             t.vat_pct, t.contract_end)).fetchone()[0]
    return {"id": tid}


@router.delete("/tariffs/{tariff_id}")
def delete_tariff(tariff_id: int):
    with pool().connection() as con:
        con.execute("DELETE FROM tariffs WHERE id = %s", (tariff_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- readings

class ReadingIn(BaseModel):
    day: date
    value: float = Field(ge=0, lt=1e9)
    estimated: bool = False
    note: str | None = Field(None, max_length=200)


@router.post("/meters/{meter_id}/readings")
def add_reading(meter_id: int, r: ReadingIn):
    with pool().connection() as con:
        con.execute("""INSERT INTO meter_readings (meter_id, day, value, estimated, note) VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (meter_id, day) DO UPDATE SET value = excluded.value,
                       estimated = excluded.estimated, note = excluded.note""",
                    (meter_id, r.day, r.value, r.estimated, r.note))
    return {"ok": True}


@router.delete("/meters/{meter_id}/readings/{day}")
def delete_reading(meter_id: int, day: date):
    with pool().connection() as con:
        con.execute("DELETE FROM meter_readings WHERE meter_id = %s AND day = %s", (meter_id, day))
    return {"ok": True}


# --------------------------------------------------------------------------- installment plans

class PlanIn(BaseModel):
    valid_from: date
    valid_to: date | None = None
    amount_gross: float = Field(ge=0, lt=100000)
    note: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def _range(self):
        if self.valid_to and self.valid_to < self.valid_from:
            raise ValueError("valid_to before valid_from")
        return self


@router.post("/meters/{meter_id}/plans")
def add_plan(meter_id: int, p: PlanIn):
    with pool().connection() as con:
        pid = con.execute("INSERT INTO installment_plans (meter_id, valid_from, valid_to, amount_gross, note) "
                          "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                          (meter_id, p.valid_from, p.valid_to, p.amount_gross, p.note)).fetchone()[0]
    return {"id": pid}


@router.put("/plans/{plan_id}")
def update_plan(plan_id: int, p: PlanIn):
    with pool().connection() as con:
        con.execute("UPDATE installment_plans SET valid_from = %s, valid_to = %s, amount_gross = %s, note = %s "
                    "WHERE id = %s", (p.valid_from, p.valid_to, p.amount_gross, p.note, plan_id))
    return {"ok": True}


@router.delete("/plans/{plan_id}")
def delete_plan(plan_id: int):
    with pool().connection() as con:
        con.execute("DELETE FROM installment_plans WHERE id = %s", (plan_id,))
    return {"ok": True}


# --------------------------------------------------------------------------- payments

class PaymentIn(BaseModel):
    meter_id: int | None = None
    day: date
    amount: float = Field(ge=-1e6, le=1e6)
    kind: str = Field("installment", pattern="^(installment|settlement|other)$")
    note: str | None = Field(None, max_length=200)
    external_ref: str | None = Field(None, max_length=120)


@router.get("/payments")
def list_payments():
    with pool().connection() as con:
        rows = con.execute("SELECT p.id, p.meter_id, p.day, p.amount, p.kind, p.note, p.external_ref "
                           "FROM payments p ORDER BY p.day DESC, p.id").fetchall()
        years = costs.payments_by_year(con)
    return {"payments": [{"id": r[0], "meter_id": r[1], "day": r[2].isoformat(), "amount": float(r[3]),
                          "kind": r[4], "note": r[5], "external_ref": r[6]} for r in rows],
            "by_year": years}


@router.post("/payments")
def add_payment(p: PaymentIn):
    with pool().connection() as con:
        row = con.execute("INSERT INTO payments (meter_id, day, amount, kind, note, external_ref) "
                          "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (external_ref) DO NOTHING RETURNING id",
                          (p.meter_id, p.day, p.amount, p.kind, p.note, p.external_ref)).fetchone()
    return {"id": row[0] if row else None, "duplicate": row is None}


class PaymentPatch(BaseModel):
    meter_id: int | None = None


@router.patch("/payments/{payment_id}")
def assign_payment(payment_id: int, p: PaymentPatch):
    with pool().connection() as con:
        con.execute("UPDATE payments SET meter_id = %s WHERE id = %s", (p.meter_id, payment_id))
    return {"ok": True}


@router.delete("/payments/{payment_id}")
def delete_payment(payment_id: int):
    with pool().connection() as con:
        con.execute("DELETE FROM payments WHERE id = %s", (payment_id,))
    return {"ok": True}
