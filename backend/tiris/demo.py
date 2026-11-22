"""Demo mode (TIRIS_DEMO=true): made-up devices that behave like real ones, no plugs and no Tapo account needed.

One behaviour model per device gives a plausible power for any moment. The same model seeds 14 months of history
(monthly, daily, hourly, 5-minute values, a day of raw samples) and drives the live values, so the views agree with
each other. A meter, a tariff, readings, an installment plan and payments make the cost views work too.

The plugs are simulated by DemoPlug, which answers the handful of calls tiris makes (meter data, device info,
timer, switching). Schedules and firmware updates are not simulated.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from types import SimpleNamespace

from psycopg_pool import ConnectionPool

from .config import Settings, settings

log = logging.getLogger("tiris.demo")


@dataclass(frozen=True)
class DemoDevice:
    id: str
    name: str
    room: str
    category: str
    pf: float            # power factor, for a plausible current
    protected: bool = False


DEVICES = [
    DemoDevice("DEMO0001", "Desk", "Office", "IT", 0.92),
    DemoDevice("DEMO0002", "Fridge", "Kitchen", "Cooling", 0.58, protected=True),
    DemoDevice("DEMO0003", "Washing machine", "Bathroom", "Household", 0.95),
    DemoDevice("DEMO0004", "TV", "Living room", "Media", 0.9),
    DemoDevice("DEMO0005", "Router & NAS", "Hall", "Network", 0.65, protected=True),
    DemoDevice("DEMO0006", "Coffee machine", "Kitchen", "Kitchen", 0.99),
    DemoDevice("DEMO0007", "Floor lamp", "Living room", "Light", 0.9),
]
IP = {d.id: f"10.0.0.{11 + i}" for i, d in enumerate(DEVICES)}
REST_KWH_DAY = 2.6    # the household beyond the plugs (light, stove, ...), for the meter readings


def _noise(key: str, t: int) -> float:
    """Deterministic noise in [-1, 1] per device and time step, so history and live agree."""
    h = hashlib.blake2b(f"{key}:{t}".encode(), digest_size=4).digest()
    return int.from_bytes(h, "big") / 0xFFFFFFFF * 2 - 1


def power(dev_id: str, t: datetime) -> float:
    """Power in W of a demo device at local time t."""
    m = t.hour * 60 + t.minute
    minute_no = int(t.timestamp() // 60)
    n = _noise(dev_id, minute_no)
    weekend = t.weekday() >= 5
    winter = 0.5 + 0.5 * math.cos((t.timetuple().tm_yday - 15) / 365 * 2 * math.pi)   # 1 in January, 0 in July
    if dev_id == "DEMO0001":           # desk: work hours on weekdays, evenings, standby at night
        if not weekend and 8 * 60 <= m < 18 * 60:
            return 150 + 35 * n
        if 18 * 60 <= m < 23 * 60 or (weekend and 10 * 60 <= m < 23 * 60):
            return 80 + 20 * n
        return 9 + n
    if dev_id == "DEMO0002":           # fridge: 22 of every 70 minutes, a start peak, more in summer
        period = 70 - 8 * (1 - winter)
        phase = (minute_no + 13) % period
        if phase < 1:
            return 430 + 40 * n
        if phase < 22:
            return 74 - phase * 0.4 + 3 * n
        return 0.0
    if dev_id == "DEMO0003":           # washing machine: every third day and on Saturdays at 10:00
        runs = t.toordinal() % 3 == 0 or t.weekday() == 5
        k = m - 10 * 60
        if runs and 0 <= k < 115:
            if k < 18:
                return 2050 + 60 * n
            if k < 100:
                return 180 + (420 if k % 5 == 0 else 0) + 30 * n
            return 460 + 80 * n
        return 0.6
    if dev_id == "DEMO0004":           # TV in the evening, longer at weekends
        start = 17 * 60 if weekend else 19 * 60
        return 92 + 8 * n if start <= m < 22 * 60 + 45 else 0.4
    if dev_id == "DEMO0005":           # router and NAS around the clock
        return 31 + 2.5 * n
    if dev_id == "DEMO0006":           # coffee: morning and after lunch, a keep-warm pulse in between
        if 7 * 60 + 10 <= m < 7 * 60 + 14 or 13 * 60 + 30 <= m < 13 * 60 + 34:
            return 1250 + 40 * n
        if 7 * 60 + 14 <= m < 9 * 60 and m % 15 == 0:
            return 600.0
        return 0.8
    if dev_id == "DEMO0007":           # lamp: from dusk (earlier in winter) until 23:00
        on_from = (16 + 3 * (1 - winter)) * 60
        return 9.2 + 0.2 * n if on_from <= m < 23 * 60 else 0.0
    return 0.0


# ---------------------------------------------------------------------------------------------- seeding
def seed(db: ConnectionPool) -> bool:
    """Fill an empty database with demo devices, history, a meter and payments. Returns False if devices exist."""
    tz = settings().tz
    with db.connection() as con:
        if con.execute("SELECT 1 FROM devices LIMIT 1").fetchone():
            return False
        now = datetime.now(tz).replace(second=0, microsecond=0)
        first = (now.date().replace(day=1) - timedelta(days=400)).replace(day=1)
        log.info("seeding demo data from %s", first)
        with con.transaction():
            for d in DEVICES:
                con.execute(
                    """INSERT INTO devices (device_id, nickname, model, ip, mac, fw_ver, hw_ver, timezone, room,
                                            category, protected, first_seen, last_seen)
                       VALUES (%s, %s, 'P110', %s, %s, '1.4.8 Build 260804', '1.0', %s, %s, %s, %s, %s, %s)""",
                    (d.id, d.name, IP[d.id], f"00-00-5E-00-53-{11 + DEVICES.index(d):02X}", str(tz), d.room,
                     d.category, d.protected, datetime.combine(first, time(0), tz), now))
            hourly, daily, monthly, five = {}, {}, {}, []
            t = datetime.combine(first, time(0), tz)
            step = timedelta(minutes=5)
            while t < now:
                for d in DEVICES:
                    wh = power(d.id, t) * 5 / 60
                    month = t.date().replace(day=1)
                    monthly[(d.id, month)] = monthly.get((d.id, month), 0) + wh
                    if t.date() >= now.date() - timedelta(days=120):
                        daily[(d.id, t.date())] = daily.get((d.id, t.date()), 0) + wh
                    if t >= now - timedelta(days=35):
                        hour = t.replace(minute=0)
                        hourly[(d.id, hour)] = hourly.get((d.id, hour), 0) + wh
                    if t >= now - timedelta(days=10):
                        five.append((d.id, t, round(power(d.id, t))))
                t += step
            with con.cursor() as cur:
                with cur.copy("COPY energy_monthly (device_id, month, wh, updated_at) FROM STDIN") as cp:
                    for (did, m), wh in monthly.items():
                        cp.write_row((did, m, round(wh), now))
                with cur.copy("COPY energy_daily (device_id, day, wh, updated_at) FROM STDIN") as cp:
                    for (did, dd), wh in daily.items():
                        cp.write_row((did, dd, round(wh), now))
                with cur.copy("COPY energy_hourly (device_id, ts, wh, updated_at) FROM STDIN") as cp:
                    for (did, h), wh in hourly.items():
                        cp.write_row((did, h, round(wh), now))
                with cur.copy("COPY power_5min (device_id, ts, w, updated_at) FROM STDIN") as cp:
                    for did, ts, w in five:
                        cp.write_row((did, ts, w, now))
                # raw samples for the last 26 hours (20 s), with the energy counter
                with cur.copy("COPY power_samples (device_id, ts, w, v, a, energy_mwh, delta_mwh) FROM STDIN") as cp:
                    for d in DEVICES:
                        e = 0.0
                        ts = now - timedelta(hours=26)
                        while ts < now:
                            w = power(d.id, ts)
                            v = 230 + 2.5 * _noise("v", int(ts.timestamp() // 60))
                            delta = w * 20 / 3.6       # mWh in 20 s
                            e += delta
                            cp.write_row((d.id, ts, round(w, 2), round(v, 1), round(w / v / d.pf, 3), round(e),
                                          round(delta)))
                            ts += timedelta(seconds=20)
            _seed_costs(con, first, now, daily, monthly)
            con.execute("INSERT INTO runs (started_at, finished_at, status, devices_ok, devices_failed, message) "
                        "VALUES (%s, %s, 'ok', %s, 0, 'demo data')", (now, now, len(DEVICES)))
    with db.connection() as con:
        con.autocommit = True
        for v in ("power_1m", "power_15m", "power_1h"):
            con.execute(f"CALL refresh_continuous_aggregate('{v}', NULL, NULL)")
    log.info("demo data ready")
    return True


def _seed_costs(con, first: date, now: datetime, daily: dict, monthly: dict) -> None:
    start = (now.date().replace(day=1) - timedelta(days=200)).replace(day=1)   # billing year started ~7 months ago
    meter = con.execute("INSERT INTO meters (kind, name, number, unit) "
                        "VALUES ('electricity', 'Electricity', 'DEMO-1', 'kWh') "
                        "RETURNING id").fetchone()[0]
    con.execute("""INSERT INTO tariffs (meter_id, valid_from, provider, name, energy_ct_net, base_eur_year_net, vat_pct,
                                        contract_end)
                   VALUES (%s, %s, 'Demo Energy', 'Basic', 24.37, 138.00, 19, %s)""",
                (meter, start - timedelta(days=365), start + timedelta(days=730)))
    # readings: plugs (monthly model) plus the rest of the household, every quarter
    def plugs_kwh(a: date, b: date) -> float:
        tot = 0.0
        m = a.replace(day=1)
        while m < b:
            nxt = (m + timedelta(days=32)).replace(day=1)
            month_wh = sum(wh for (_, mm), wh in monthly.items() if mm == m)
            days_in = (nxt - m).days
            lo, hi = max(a, m), min(b, nxt)
            tot += month_wh / 1000 * max(0, (hi - lo).days) / days_in
            m = nxt
        return tot
    value = 31_250.0
    day = start
    readings = []
    while day <= now.date() - timedelta(days=3):
        readings.append((day, round(value, 1)))
        nxt = min((day + timedelta(days=92)), now.date() - timedelta(days=3))
        if nxt <= day:
            break
        value += plugs_kwh(day, nxt) + REST_KWH_DAY * (nxt - day).days
        day = nxt
    # the first reading is the last bill (the billing year starts the day after); later ones are own readings that
    # tiris treats like estimates, so they refine the forecast without starting a new billing year
    for i, (dd, v) in enumerate(readings):
        con.execute("INSERT INTO meter_readings (meter_id, day, value, estimated, note) VALUES (%s, %s, %s, %s, %s)",
                    (meter, dd, v, i > 0, None if i == 0 else "own reading"))
    con.execute("INSERT INTO installment_plans (meter_id, valid_from, amount_gross, note) "
                "VALUES (%s, %s, 68, 'installment')",
                (meter, start.replace(day=15)))
    d = start.replace(day=15)
    while d <= now.date():
        con.execute("INSERT INTO payments (meter_id, day, amount, kind, note) "
                    "VALUES (%s, %s, 68, 'installment', NULL)",
                    (meter, d))
        d = (d + timedelta(days=32)).replace(day=15)


# ---------------------------------------------------------------------------------------------- simulated plugs
class DemoPlug:
    """Answers the calls tiris makes to a P110, from the behaviour model."""

    def __init__(self, dev: DemoDevice, energy_mwh: float):
        self.dev = dev
        self.on_state = True
        self.since = datetime.now(settings().tz) - timedelta(days=12, hours=3)
        self.energy = energy_mwh
        self.last = datetime.now(settings().tz)
        self.timer: tuple[float, bool, int] | None = None     # (due unix time, turn on?, delay s)

    def _tick(self) -> float:
        now = datetime.now(settings().tz)
        if self.timer and now.timestamp() >= self.timer[0]:
            self._set(self.timer[1])
            self.timer = None
        w = power(self.dev.id, now) if self.on_state else 0.0
        self.energy += w * (now - self.last).total_seconds() / 3.6
        self.last = now
        return w

    def _set(self, on: bool) -> None:
        if on != self.on_state:
            self.on_state = on
            self.since = datetime.now(settings().tz)

    async def get_energy_meter_data(self):
        w = self._tick()
        v = 230 + 2.5 * _noise("v", int(datetime.now().timestamp() // 60))
        return SimpleNamespace(power_mw=round(w * 1000), voltage_mv=round(v * 1000),
                               current_ma=round(w / v / self.dev.pf * 1000) if w else 0, energy_mwh=round(self.energy))

    async def get_device_info(self):
        self._tick()
        on_time = int((datetime.now(settings().tz) - self.since).total_seconds()) if self.on_state else 0
        info = {"device_on": self.on_state, "rssi": -48 - DEVICES.index(self.dev) * 3,
                "signal_level": 3 if DEVICES.index(self.dev) < 5 else 2, "on_time": on_time,
                "fw_ver": "1.4.8 Build 260804", "hw_ver": "1.0", "overcurrent_status": "normal",
                "overheat_status": None, "power_protection_status": "normal", "default_states": {"type": "last_states"},
                "nickname": self.dev.name, "model": "P110"}
        return SimpleNamespace(to_dict=lambda: info)

    async def get_timer(self):
        if not self.timer:
            return None
        from tapo.responses import PowerState
        left = max(0, int(self.timer[0] - datetime.now().timestamp()))
        return SimpleNamespace(remaining_s=left, delay_s=self.timer[2],
                               desired_state=PowerState.On if self.timer[1] else PowerState.Off)

    async def set_timer(self, delay_s: int, state):
        from tapo.responses import PowerState  # tiris passes the library's PowerState
        self.timer = (datetime.now().timestamp() + delay_s, state == PowerState.On, delay_s)
        return SimpleNamespace(remaining_s=delay_s)

    async def clear_timer(self):
        self.timer = None

    async def on(self):
        self._tick()
        self._set(True)

    async def off(self):
        self._tick()
        self._set(False)

    async def set_nickname(self, name: str):
        return None

    async def device_reboot(self, delay_s: int = 3):
        return None

    async def get_latest_firmware(self):
        return SimpleNamespace(to_dict=lambda: {"update_available": False, "fw_ver": "1.4.8 Build 260804"})

    async def get_schedule_rules(self):
        return []

    async def get_max_schedule_rules(self):
        return 32

    async def _not_in_demo(self, *_a, **_k):
        raise RuntimeError("schedules are not simulated in demo mode")

    add_schedule_rule = edit_schedule_rule = remove_schedule_rule = _not_in_demo
    get_firmware_update_state = start_firmware_update = _not_in_demo


class DemoPlugPool:
    """Stands in for PlugPool in demo mode."""
    demo = True

    def __init__(self, s: Settings, db: ConnectionPool):
        self.settings = s
        with db.connection() as con:
            last = dict(con.execute("SELECT device_id, max(energy_mwh) FROM power_samples GROUP BY 1").fetchall())
        self._plugs = {IP[d.id]: DemoPlug(d, float(last.get(d.id) or 0)) for d in DEVICES}

    @property
    def enabled(self) -> bool:
        return True

    async def handler(self, ip: str):
        await asyncio.sleep(0)
        if ip not in self._plugs:
            raise RuntimeError(f"no demo plug at {ip}")
        return self._plugs[ip]

    def forget(self, ip: str) -> None:
        pass

    def adopt(self, ip: str, handler) -> None:
        pass
