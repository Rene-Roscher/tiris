"""Device API: list with live state, local metadata, and control of the plugs."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import pool
from ..devices import _is_on, _power_state, rule_dict
from ..state import need_devices

router = APIRouter(prefix="/api/devices")


@router.get("")
async def list_devices(firmware: bool = True):
    return {"devices": await need_devices().list(check_firmware=firmware)}


class MetaIn(BaseModel):
    room: str | None = Field(None, max_length=60)
    category: str | None = Field(None, max_length=60)
    note: str | None = Field(None, max_length=500)
    protected: bool | None = None
    retired: bool | None = None


@router.patch("/{device_id}")
def patch_meta(device_id: str, m: MetaIn):
    fields = m.model_dump(exclude_unset=True)
    if not fields:
        return {"ok": True}
    fields = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in fields.items()}
    sets = ", ".join(f"{k} = %s" for k in fields)   # keys come from the model, not from the request body
    with pool().connection() as con:
        cur = con.execute(f"UPDATE devices SET {sets} WHERE device_id = %s", (*fields.values(), device_id))
        if cur.rowcount == 0:
            raise HTTPException(404, "unknown device")
    return {"ok": True}


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@router.post("/{device_id}/rename")
async def rename(device_id: str, body: RenameIn):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "name must not be empty")
    svc = need_devices()
    d, h = await svc.handler(device_id)
    await svc.call(d["ip"], h.set_nickname(name), "rename")
    with pool().connection() as con:  # visible at once; the collector reads it from the plug anyway
        con.execute("UPDATE devices SET nickname = %s WHERE device_id = %s", (name, device_id))
    return {"ok": True, "name": name}


class PowerIn(BaseModel):
    on: bool


@router.post("/{device_id}/power")
async def power(device_id: str, body: PowerIn):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    if not body.on:
        svc.guard_off(d, "switching off")
    await svc.call(d["ip"], h.on() if body.on else h.off(), "switch")
    return {"ok": True, "on": body.on}


class TimerIn(BaseModel):
    minutes: int = Field(ge=1, le=24 * 60)
    on: bool


@router.post("/{device_id}/timer")
async def set_timer(device_id: str, body: TimerIn):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    if not body.on:
        svc.guard_off(d, "a switch-off timer")
    t = await svc.call(d["ip"], h.set_timer(body.minutes * 60, _power_state(body.on)), "set timer")
    return {"ok": True, "remaining_s": t.remaining_s}


@router.delete("/{device_id}/timer")
async def clear_timer(device_id: str):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    await svc.call(d["ip"], h.clear_timer(), "clear timer")
    return {"ok": True}


@router.get("/{device_id}/schedules")
async def list_schedules(device_id: str):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    rules = await svc.call(d["ip"], h.get_schedule_rules(), "read schedules")
    mx = await svc.call(d["ip"], h.get_max_schedule_rules(), "read schedules")
    return {"rules": [rule_dict(r) for r in rules], "max": mx}


class RuleIn(BaseModel):
    kind: str = Field("clock", pattern="^(clock|sunrise|sunset)$")
    hour: int | None = Field(None, ge=0, le=23)
    minute: int | None = Field(None, ge=0, le=59)
    offset_minutes: int | None = Field(None, ge=-720, le=720)
    days: int | None = Field(None, ge=0, le=127)   # bit mask, bit 0 = Sunday; None/0 = once
    on: bool
    enabled: bool = True


def build_rule(r: RuleIn):
    from tapo.requests import DaysOfWeek, ScheduleRule
    st = _power_state(r.on)
    days = DaysOfWeek.from_bits_truncate(r.days) if r.days else None
    if r.kind == "clock":
        if r.hour is None or r.minute is None:
            raise HTTPException(422, "time missing")
        rule = ScheduleRule.clock_weekly(r.hour, r.minute, days, st) if days else \
            ScheduleRule.clock_once(r.hour, r.minute, st)
    else:
        off = r.offset_minutes or 0
        weekly = ScheduleRule.sunrise_weekly if r.kind == "sunrise" else ScheduleRule.sunset_weekly
        once = ScheduleRule.sunrise_once if r.kind == "sunrise" else ScheduleRule.sunset_once
        rule = weekly(off, days, st) if days else once(off, st)
    return rule.with_enabled(r.enabled)


@router.post("/{device_id}/schedules")
async def add_schedule(device_id: str, body: RuleIn):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    if not body.on:
        svc.guard_off(d, "a switch-off schedule")
    res = await svc.call(d["ip"], h.add_schedule_rule(build_rule(body)), "add schedule")
    return {"ok": True, "rule": rule_dict(res)}


class RuleToggle(BaseModel):
    enabled: bool


@router.patch("/{device_id}/schedules/{rule_id}")
async def toggle_schedule(device_id: str, rule_id: str, body: RuleToggle):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    rules = await svc.call(d["ip"], h.get_schedule_rules(), "read schedules")
    r = next((x for x in rules if x.id == rule_id), None)
    if r is None:
        raise HTTPException(404, "rule not found")
    if body.enabled and not _is_on(r.desired_state):
        svc.guard_off(d, "a switch-off schedule")
    await svc.call(d["ip"], h.edit_schedule_rule(r.to_editable().with_id(rule_id).with_enabled(body.enabled)),
                   "edit schedule")
    return {"ok": True}


@router.delete("/{device_id}/schedules/{rule_id}")
async def delete_schedule(device_id: str, rule_id: str):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    await svc.call(d["ip"], h.remove_schedule_rule(rule_id), "delete schedule")
    return {"ok": True}


@router.post("/{device_id}/reboot")
async def reboot(device_id: str):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    svc.guard_off(d, "a reboot (cuts power briefly)")
    await svc.call(d["ip"], h.device_reboot(2), "reboot")
    return {"ok": True}


@router.post("/{device_id}/firmware")
async def firmware_update(device_id: str):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    svc.guard_off(d, "a firmware update (restarts the plug)")
    fw = await svc.firmware(d["ip"])
    if not fw.get("available"):
        raise HTTPException(409, "no update available")
    await svc.call(d["ip"], h.start_firmware_update(), "start firmware update")
    return {"ok": True, "version": fw.get("version")}


@router.get("/{device_id}/firmware")
async def firmware_state(device_id: str):
    svc = need_devices()
    d, h = await svc.handler(device_id)
    st = await svc.call(d["ip"], h.get_firmware_update_state(), "read update state")
    return st.to_dict()
