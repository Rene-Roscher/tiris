"""Device state and control: rename, power, timer, schedules, reboot, firmware, plus local metadata.

Not offered on purpose: factory reset (the plug would leave the account).
Protected devices cannot be switched off, get no switch-off timer or schedule, no reboot and no firmware update
through tiris; the check runs before anything reaches the plug.
"""
from __future__ import annotations

import asyncio
import logging
import time

from fastapi import HTTPException
from psycopg_pool import ConnectionPool

from .overview import color_slots
from .plugs import PlugPool

log = logging.getLogger("tiris.devices")

STATUS_TIMEOUT_S = 2.5     # a plug busy with its firmware check does not answer for up to ~10 s [measured]
FW_TTL_S = 24 * 3600       # the firmware check blocks the plug, so check rarely
FW_ERR_TTL_S = 6 * 3600
DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]  # bit 0 = Sunday (DaysOfWeek.SUN = 1)


def _power_state(on: bool):
    from tapo.responses import PowerState
    return PowerState.On if on else PowerState.Off


def _is_on(state) -> bool:
    from tapo.responses import PowerState
    return state == PowerState.On


def rule_dict(r) -> dict:
    t = r.time
    kind = type(t).__name__.lower()          # clock | sunrise | sunset
    out = {"id": r.id, "enabled": r.enabled, "kind": kind, "on": _is_on(r.desired_state),
           "days": r.days.bits() if r.days is not None else None}
    if kind == "clock":
        out |= {"hour": t.hour, "minute": t.minute}
    else:
        out["offset_minutes"] = t.offset_minutes
    return out


class DeviceService:
    def __init__(self, db: ConnectionPool, plugs: PlugPool):
        self.db, self.plugs = db, plugs
        self._status_cache: dict[str, dict] = {}
        self._fw_cache: dict[str, tuple[float, dict]] = {}
        self._fw_queue: list[str] = []
        self._fw_task: asyncio.Task | None = None
        self._fw_client = None
        self._fw_handlers: dict[str, object] = {}

    # ------------------------------------------------------------------ helpers
    def row(self, device_id: str) -> dict:
        with self.db.connection() as con:
            r = con.execute(
                "SELECT device_id, nickname, ip, protected, retired FROM devices "
                "WHERE device_id = %s AND parent_id IS NULL", (device_id,)).fetchone()
        if not r:
            raise HTTPException(404, "unknown device")
        if not r[2]:
            raise HTTPException(409, "no IP known for this device")
        return {"id": r[0], "name": r[1], "ip": r[2], "protected": r[3], "retired": r[4]}

    async def handler(self, device_id: str):
        d = self.row(device_id)
        try:
            return d, await self.plugs.handler(d["ip"])
        except Exception as exc:
            raise HTTPException(502, f"plug not reachable: {exc}") from exc

    async def call(self, ip: str, coro, what: str):
        try:
            return await asyncio.wait_for(coro, 15)
        except Exception as exc:
            self.plugs.forget(ip)
            raise HTTPException(502, f"{what} failed: {exc}") from exc

    @staticmethod
    def guard_off(d: dict, what: str) -> None:
        if d["protected"]:
            raise HTTPException(423, f"device is protected: {what} is blocked; remove the protection first")

    # ------------------------------------------------------------------ status
    async def status(self, ip: str) -> dict:
        try:
            res = await asyncio.wait_for(self._status_fetch(ip), STATUS_TIMEOUT_S)
            self._status_cache[ip] = res
            return res
        except Exception as exc:
            if ip in self._status_cache:
                return self._status_cache[ip] | {"stale": True}
            return {"reachable": False, "error": str(exc)[:200] or "timeout"}

    async def _status_fetch(self, ip: str) -> dict:
        h = await self.plugs.handler(ip)
        info, timer = await asyncio.gather(h.get_device_info(), h.get_timer())
        i = info.to_dict()  # the library's enums as strings
        ds = i.get("default_states")
        return {
            "reachable": True, "device_on": i.get("device_on"), "rssi": i.get("rssi"),
            "signal_level": i.get("signal_level"), "on_time_s": i.get("on_time"), "fw_ver": i.get("fw_ver"),
            "hw_ver": i.get("hw_ver"), "overcurrent": i.get("overcurrent_status"),
            "overheat": i.get("overheat_status"), "power_protection": i.get("power_protection_status"),
            "default_state": ds.get("type") if isinstance(ds, dict) else ds,
            "timer": {"remaining_s": timer.remaining_s, "delay_s": timer.delay_s, "on": _is_on(timer.desired_state)}
            if timer else None,
        }

    # ------------------------------------------------------------------ firmware (serial, own long-timeout client)
    async def _fw_handler(self, ip: str):
        if getattr(self.plugs, "demo", False):
            return await self.plugs.handler(ip)
        if self._fw_client is None:
            from tapo import ApiClient
            s = self.plugs.settings
            self._fw_client = ApiClient(s.tapo_username, s.tapo_password, timeout_s=30)
        h = self._fw_handlers.get(ip)
        if h is None:
            h = await asyncio.wait_for(self._fw_client.p110(ip), 12)
            self._fw_handlers[ip] = h
        return h

    def firmware_cached(self, ip: str) -> dict | None:
        hit = self._fw_cache.get(ip)
        return hit[1] if hit else None

    def firmware_fresh(self, ip: str) -> bool:
        hit = self._fw_cache.get(ip)
        return bool(hit) and time.time() - hit[0] < (FW_ERR_TTL_S if "error" in hit[1] else FW_TTL_S)

    async def firmware(self, ip: str) -> dict:
        try:
            h = await self._fw_handler(ip)
            f = (await asyncio.wait_for(h.get_latest_firmware(), 35)).to_dict()
            res = {"available": f.get("update_available"), "version": f.get("fw_ver"),
                   "release_date": str(f.get("release_date") or ""), "notes": f.get("release_notes")}
        except Exception as exc:
            self._fw_handlers.pop(ip, None)
            e = str(exc)
            code = "unreachable" if "-1001" in e else "timeout" if "TimedOut" in e else "failed"
            res = {"error": code, "detail": e[:160]}
        self._fw_cache[ip] = (time.time(), res)
        return res

    def enqueue_firmware(self, ip: str) -> None:
        if ip not in self._fw_queue:
            self._fw_queue.append(ip)
        if self._fw_task is None or self._fw_task.done():
            self._fw_task = asyncio.create_task(self._fw_run())

    async def _fw_run(self) -> None:
        while self._fw_queue:  # one plug at a time: the check blocks that plug
            ip = self._fw_queue[0]
            try:
                await self.firmware(ip)
            finally:
                self._fw_queue.pop(0)

    # ------------------------------------------------------------------ list
    async def list(self, check_firmware: bool = True) -> list[dict]:
        with self.db.connection() as con:
            rows = con.execute(
                """SELECT device_id, COALESCE(nickname, device_id), model, ip, mac, hw_ver, first_seen, last_seen,
                          retired, room, category, note, protected
                   FROM devices WHERE parent_id IS NULL ORDER BY retired, nickname""").fetchall()
            slots = color_slots(con)
        active = [r for r in rows if r[3] and not r[8]]
        statuses = await asyncio.gather(*(self.status(r[3]) for r in active))
        by_id = dict(zip((r[0] for r in active), statuses, strict=True))
        out = []
        for r in rows:
            ip = r[3]
            if check_firmware and ip and not r[8] and not self.firmware_fresh(ip):
                self.enqueue_firmware(ip)
            fw = self.firmware_cached(ip) if ip else None
            out.append({
                "id": r[0], "name": r[1].strip(), "model": r[2], "ip": ip, "mac": r[4], "hw_ver": r[5],
                "first_seen": r[6].isoformat() if r[6] else None, "last_seen": r[7].isoformat() if r[7] else None,
                "retired": r[8], "room": r[9], "category": r[10], "note": r[11], "protected": r[12],
                "slot": slots.get(r[0], 0),
                "status": by_id.get(r[0], {"reachable": False}),
                "firmware": fw or ({"pending": True} if ip in self._fw_queue else None),
            })
        return out
