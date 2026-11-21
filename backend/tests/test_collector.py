"""Collector scenarios against a real TimescaleDB with simulated plugs (ported from an earlier prototype).

The fake plugs follow the documented library rules and what real P110 plugs did (2026-11-21):
- hourly windows <= 8 days, 24 entries per local day; spring-forward hour has the start of the next hour,
  fall-back hour is one entry; daily windows start at a quarter, monthly at a year; nothing after "now";
- retention like the app (7 days hourly, ~92 days daily, 12 months monthly), zeros beyond it;
- optional: replaying the current buffer for old windows, shifted old daily windows, per-hour rounding.

Run:  TIRIS_TEST_DATABASE_URL=postgresql://user:pw@host:port/empty_db  uv run pytest
The tests drop and recreate the schema of that database. Never point it at real data.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import psycopg
import pytest
from psycopg_pool import ConnectionPool
from tapo.requests import EnergyDataInterval

from tiris import collector, db, history

URL = os.environ.get("TIRIS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TIRIS_TEST_DATABASE_URL not set")
TZ = ZoneInfo("Europe/Berlin")
H = timedelta(hours=1)
NOW = datetime(2026, 11, 21, 0, 20, tzinfo=TZ)


# ----------------------------------------------------------------------------- fake plug


def hour_wh(seed: int, utc_start: datetime) -> int:
    n = int(utc_start.timestamp()) // 3600
    return 5 + (n * 2654435761 + seed * 97) % 61


def local_day_utc_hours(d: date):
    t = datetime.combine(d, time(0), TZ).astimezone(UTC)
    end = datetime.combine(d + timedelta(days=1), time(0), TZ).astimezone(UTC)
    while t < end:
        yield t
        t += H


@dataclass
class FakePlug:
    seed: int
    installed: date
    now_local: datetime = NOW
    liar: bool = False
    wiped: bool = False
    auth_fail: bool = False
    quiet_since: date | None = None
    keep_all_days: bool = False
    shift_old_daily: bool = False
    rounding: bool = False
    calls: list = field(default_factory=list)

    def true_hour(self, utc: datetime) -> int:
        if utc.astimezone(TZ).date() < self.installed or utc > self.now_local.astimezone(UTC):
            return 0
        if self.quiet_since and utc.astimezone(TZ).date() >= self.quiet_since:
            return 0
        return hour_wh(self.seed, utc)

    def true_day(self, d: date) -> int:
        return sum(self.true_hour(u) for u in local_day_utc_hours(d))

    def true_month(self, m: date) -> int:
        d, total = m, 0
        while d.month == m.month and d <= self.now_local.date():
            total += self.true_day(d)
            d += timedelta(days=1)
        return total

    @property
    def today(self) -> date:
        return self.now_local.date()

    def keeps_hour(self, utc: datetime) -> bool:
        return utc >= datetime.combine(self.today - timedelta(days=7), time(0), TZ).astimezone(UTC)

    def keeps_day(self, d: date) -> bool:
        return d >= self.today - timedelta(days=365 if self.keep_all_days else 92)

    def keeps_month(self, m: date) -> bool:
        first = self.today.replace(day=1)
        y, mo = first.year, first.month - 11
        while mo <= 0:
            y, mo = y - 1, mo + 12
        return m >= date(y, mo, 1)

    async def get_timezone(self):
        if self.auth_fail:
            raise Exception("Tapo(TpapCredentials): invalid credentials")
        return SimpleNamespace(timezone=TZ)

    async def get_power_data(self, *_a, **_k):
        return SimpleNamespace(entries=[])

    def _hourly(self, start: date, end: date):
        out, d = [], start
        while d <= end:
            for hh in range(24):
                wall = datetime.combine(d, time(hh))
                a, b = wall.replace(tzinfo=TZ, fold=0), wall.replace(tzinfo=TZ, fold=1)
                if a.utcoffset() != b.utcoffset() and a.astimezone(UTC).astimezone(TZ).replace(tzinfo=None) == wall:
                    st, real = a.astimezone(UTC), [a.astimezone(UTC), b.astimezone(UTC)]  # fall back: one entry
                elif a.astimezone(UTC).astimezone(TZ).replace(tzinfo=None) != wall:
                    st, real = (wall + H).replace(tzinfo=TZ).astimezone(UTC), []  # spring forward
                else:
                    st, real = a.astimezone(UTC), [a.astimezone(UTC)]
                if st > self.now_local.astimezone(UTC):
                    continue
                wh = sum(self.true_hour(u) for u in real) if self.keeps_hour(st) else 0
                if self.rounding and wh and st.hour % 4 == 0:
                    wh += 1
                out.append(SimpleNamespace(start_date_time=st, energy=wh))
            d += timedelta(days=1)
        return out

    def _daily(self, start: date, end: date):
        out, d = [], start
        shift = (
            timedelta(days=30) if self.shift_old_daily and start < self.today - timedelta(days=365) else timedelta(0)
        )
        while d <= end and d <= self.today:
            src = d - shift
            out.append(
                SimpleNamespace(
                    start_date_time=datetime.combine(d, time(0), TZ).astimezone(UTC),
                    energy=self.true_day(src) if self.keeps_day(src) else 0,
                )
            )
            d += timedelta(days=1)
        return out

    def _monthly(self, start: date, end: date):
        out = []
        for mo in range(1, 13):
            m = date(start.year, mo, 1)
            if m > end or m > self.today:
                break
            out.append(
                SimpleNamespace(
                    start_date_time=datetime.combine(m, time(0), TZ).astimezone(UTC),
                    energy=self.true_month(m) if self.keeps_month(m) else 0,
                )
            )
        return out

    async def get_energy_data(self, interval, start_date, end_date=None, timezone=None):
        assert timezone == TZ
        self.calls.append((str(interval), start_date, end_date))
        if interval == EnergyDataInterval.Hourly:
            assert (end_date - start_date).days + 1 <= 8, "hourly window > 8 days"
            entries, newest, gen = (
                self._hourly(start_date, end_date),
                (self.today - timedelta(days=7), self.today),
                self._hourly,
            )
        elif interval == EnergyDataInterval.Daily:
            assert start_date == history.quarter_start(start_date), f"daily start not a quarter start: {start_date}"
            entries, newest, gen = (
                self._daily(start_date, end_date),
                (history.quarter_start(self.today), self.today),
                self._daily,
            )
        else:
            assert (start_date.month, start_date.day) == (1, 1), "monthly start not a year start"
            entries, newest, gen = (
                self._monthly(start_date, end_date),
                (date(self.today.year, 1, 1), self.today),
                self._monthly,
            )
        if self.liar and start_date < newest[0]:
            buf = gen(*newest)
            entries = [
                SimpleNamespace(start_date_time=e.start_date_time, energy=buf[i].energy if i < len(buf) else 0)
                for i, e in enumerate(entries)
            ]
        if self.wiped:
            entries = [SimpleNamespace(start_date_time=e.start_date_time, energy=0) for e in entries]
        return SimpleNamespace(entries=entries)


def target(did: str, dev: FakePlug) -> history.EnergyTarget:
    t = history.EnergyTarget(
        device_id=did,
        nickname=did,
        model="P110",
        handler=dev,
        ip=f"192.0.2.{dev.seed}",
        mac="AA",
        fw_ver="1.4.8",
        hw_ver="1.0",
    )
    t.address = (t.ip, 80)  # what discovery results carry
    return t


class FakePlugs:
    """Stands in for PlugPool: discovery returns the given targets (some only on the second attempt)."""

    def __init__(self, targets: list, lazy: frozenset = frozenset()):
        self.targets, self.lazy, self.calls, self.adopted = targets, lazy, 0, {}

    async def discover(self, known):
        self.calls += 1
        found = {t.device_id: t for t in self.targets if self.calls > 1 or t.device_id not in self.lazy}
        return history.DiscoveryOutcome(parents=found, errors=[], ignored=[])

    def adopt(self, ip, h):
        self.adopted[ip] = h


# ----------------------------------------------------------------------------- harness


@pytest.fixture
def pool():
    with psycopg.connect(URL, autocommit=True) as con:
        con.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    db.migrate(URL)
    p = ConnectionPool(URL, min_size=1, max_size=4, open=True)
    yield p
    p.close()


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    state = {"now": NOW}

    async def expand(res):
        return [res]

    monkeypatch.setattr(history, "expand_targets", expand)
    monkeypatch.setattr(history, "local_today", lambda tz: state["now"].astimezone(tz).date())
    monkeypatch.setattr(collector, "utcnow", lambda: state["now"].astimezone(UTC))
    return state


async def run(pool, clock, targets: list, now: datetime, backfill=False) -> dict:
    clock["now"] = now
    for t in targets:
        t.handler.now_local = now
        t.handler.calls.clear()
    return await collector.collect(pool, FakePlugs(targets), force_backfill=backfill)


def q(pool, sql, params=None):
    with pool.connection() as con:
        return con.execute(sql, params).fetchall()


# ----------------------------------------------------------------------------- scenarios


async def test_first_run_backfill(pool, fake_clock):
    old, new = FakePlug(seed=1, installed=date(2024, 6, 1)), FakePlug(seed=2, installed=NOW.date() - timedelta(days=20))
    t_old, t_new = target("dev-old", old), target("dev-new", new)
    r = await run(pool, fake_clock, [t_old, t_new], NOW)
    assert r["status"] == "ok", r
    today = NOW.date()
    rows = dict(q(pool, "SELECT ts, wh FROM energy_hourly WHERE device_id = 'dev-old'"))
    first = datetime.combine(today - timedelta(days=7), time(0), TZ).astimezone(UTC)
    exp, t = {}, first
    while t <= NOW.astimezone(UTC):
        exp[t] = old.true_hour(t)
        t += H
    assert {k: v for k, v in rows.items() if v} == {k: v for k, v in exp.items() if v}
    days = dict(q(pool, "SELECT day, wh FROM energy_daily WHERE device_id = 'dev-old' AND wh > 0"))
    assert min(days) == today - timedelta(days=92) and len(days) == 93
    assert all(days[d] == old.true_day(d) for d in days)
    months = dict(q(pool, "SELECT month, wh FROM energy_monthly WHERE device_id = 'dev-old' AND wh > 0"))
    assert len(months) == 12 and all(months[m] == old.true_month(m) for m in months)
    nd = dict(q(pool, "SELECT day, wh FROM energy_daily WHERE device_id = 'dev-new' AND wh > 0"))
    assert min(nd) == new.installed
    assert len(old.calls) == 11, old.calls  # backfill: monthly 4, daily 4, hourly 3

    before = q(pool, "SELECT COUNT(*), SUM(wh) FROM energy_daily")
    r = await run(pool, fake_clock, [t_old, t_new], NOW)
    assert r["status"] == "ok" and len(old.calls) == 5  # normal run: 5 requests
    assert q(pool, "SELECT COUNT(*), SUM(wh) FROM energy_daily") == before

    old.wiped = True  # "delete energy data" in the app
    await run(pool, fake_clock, [t_old, t_new], NOW)
    assert q(pool, "SELECT COUNT(*), SUM(wh) FROM energy_daily") == before


async def test_daily_operation_and_outage(pool, fake_clock):
    dev = FakePlug(seed=3, installed=date(2025, 1, 1))
    t = target("dev-ops", dev)
    start = (NOW - timedelta(days=40)).date()
    for i in range(31):  # 31 days of daily runs across the end of DST (2026-10-25)
        r = await run(pool, fake_clock, [t], datetime.combine(start + timedelta(days=i), time(0, 20), TZ))
        assert r["status"] == "ok"
    last = datetime.combine(start + timedelta(days=30), time(0, 20), TZ)
    dev.now_local = last
    span = q(pool, "SELECT MAX(ts) - MIN(ts) FROM energy_hourly WHERE device_id = 'dev-ops'")[0][0]
    assert span.days >= 37
    days = dict(q(pool, "SELECT day, wh FROM energy_daily WHERE device_id = 'dev-ops' AND day < %s", (last.date(),)))
    assert not [
        d for d, wh in days.items() if wh != dev.true_day(d) and dev.keeps_day(d)
    ]  # partial values grew to final
    oct25 = date(2026, 10, 25)
    n = q(
        pool,
        "SELECT COUNT(*) FROM energy_hourly WHERE device_id = 'dev-ops' "
        "AND (ts AT TIME ZONE 'Europe/Berlin')::date = %s",
        (oct25,),
    )[0][0]
    assert n == 24 and days[oct25] == dev.true_day(oct25)

    after = datetime.combine(last.date() + timedelta(days=9), time(0, 20), TZ)  # 9 days down
    assert (await run(pool, fake_clock, [t], after))["status"] == "ok"
    gap_days = q(
        pool,
        """SELECT g::date FROM generate_series(%s::date, %s::date - 1, interval '1 day') g
                          WHERE NOT EXISTS (SELECT 1 FROM energy_daily
                                            WHERE device_id = 'dev-ops' AND day = g::date)""",
        (last.date(), after.date()),
    )
    assert gap_days == []  # days survive a 9-day outage, hours do not (device keeps 7)


async def test_spring_forward(pool, fake_clock):
    dev = FakePlug(seed=4, installed=date(2025, 1, 1))
    assert (await run(pool, fake_clock, [target("dev-dst", dev)], datetime(2026, 4, 2, 0, 20, tzinfo=TZ)))[
        "status"
    ] == "ok"
    n, s = q(
        pool,
        "SELECT COUNT(*), SUM(wh) FROM energy_hourly WHERE device_id = 'dev-dst' "
        "AND (ts AT TIME ZONE 'Europe/Berlin')::date = '2026-03-29'",
    )[0]
    assert n == 23 and s == dev.true_day(date(2026, 3, 29))


async def test_replaying_plug(pool, fake_clock):
    dev = FakePlug(seed=5, installed=date(2024, 1, 1), liar=True)
    r = await run(pool, fake_clock, [target("dev-liar", dev)], NOW)
    assert r["status"] == "partial" and any("repeats a newer window" in e for e in r["errors"])
    assert q(pool, "SELECT MIN(day) FROM energy_daily")[0][0] >= history.quarter_start(NOW.date())


async def test_quiet_plug_is_not_a_replay(pool, fake_clock):
    assert not history._looks_replayed([0] * 52 + [5, 7, 9] + [0] * 36, [[0] * 52])
    assert not history._looks_replayed([5] * 90, [[5] * 90])
    assert history._looks_replayed([3, 8, 1, 9] + [0] * 80, [[3, 8, 1, 9]])
    dev = FakePlug(seed=11, installed=date(2026, 3, 20), quiet_since=date(2026, 9, 10), keep_all_days=True)
    r = await run(pool, fake_clock, [target("dev-q", dev)], NOW)
    assert r["status"] == "ok", r
    days = dict(q(pool, "SELECT day, wh FROM energy_daily WHERE device_id = 'dev-q' AND wh > 0"))
    assert min(days) == date(2026, 3, 20) and all(days[d] == dev.true_day(d) for d in days)


async def test_misdated_windows_are_dropped(pool, fake_clock):
    dev = FakePlug(seed=12, installed=date(2025, 3, 1), keep_all_days=True, shift_old_daily=True)
    dev.keeps_day = lambda d: d >= date(2025, 3, 1)
    r = await run(pool, fake_clock, [target("dev-m", dev)], NOW, backfill=True)
    assert r["status"] == "ok" and any("misdated" in w for w in r["warnings"])
    days = dict(q(pool, "SELECT day, wh FROM energy_daily WHERE device_id = 'dev-m'"))
    assert not [d for d, wh in days.items() if wh != dev.true_day(d)]
    assert min(days) >= date(2025, 10, 1)


async def test_rounding_is_tolerated(pool, fake_clock):
    dev = FakePlug(seed=13, installed=date(2025, 1, 1), rounding=True)
    r = await run(pool, fake_clock, [target("dev-r", dev)], NOW)
    assert r["status"] == "ok" and not r["warnings"], r


async def test_missing_plug_and_auth_error(pool, fake_clock):
    a, b = FakePlug(seed=6, installed=date(2025, 1, 1)), FakePlug(seed=7, installed=date(2025, 1, 1))
    ta, tb = target("dev-a", a), target("dev-b", b)
    await run(pool, fake_clock, [ta, tb], NOW)
    r = await run(pool, fake_clock, [ta], NOW)
    assert r["status"] == "partial" and any("not reachable" in e for e in r["errors"])
    b.auth_fail = True
    r = await run(pool, fake_clock, [ta, tb], NOW)
    assert r["status"] == "partial" and b.calls == []  # auth errors are never retried (TPAP lockout)
