"""Device history from the plugs: hourly, daily and monthly energy plus the 5-minute power buffer.

Ported from an earlier prototype, where it was checked against real P110 plugs
(FW 1.4.7 / 1.4.8, 2026-11-21) and covered by scenario tests:
- backfill as far as each plug keeps data, normal runs re-read a safety window;
- zeros are only trusted where the plug surely still holds data;
- each level is checked against the coarser one; windows that do not fit (misdated) or repeat a newer window
  (replay) are dropped and stop the backfill for that level.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from tapo import ApiClient, DiscoveryResult
from tapo.requests import EnergyDataInterval, PowerDataInterval

log = logging.getLogger("tiris.history")

AUTH_ERROR_MARKERS = ("credential", "authattempts", "forbidden", "hashmismatch")

# Backfill limits (first contact with a device, or an explicit backfill).
BACKFILL_HOURLY_WINDOWS = 12     # up to 12 x 8 days; busy plugs keep ~8 days, rarely used ones up to ~30 [measured]
BACKFILL_QUARTERS = 8            # ask 2 years of daily values; the app shows 3 months
BACKFILL_OLDEST_YEAR = 2020      # monthly values; the app shows 12 months
BACKFILL_EMPTY_STOP = 2          # stop after this many empty windows in a row

# How far back a 0 from the plug counts as a real 0. Beyond its memory the plug also returns 0 instead of
# "unknown". Shorter on purpose than the app's display windows (7 days / 3 months / 12 months), because user
# reports show shorter daily history (python-kasa #746: ~69 days).
TRUST_ZERO_HOURLY_DAYS = 6
TRUST_ZERO_DAILY_DAYS = 60
TRUST_ZERO_MONTHS = 6


def is_auth_error(exc: BaseException) -> bool:
    msg = str(exc).lower().replace("_", "")
    return any(m in msg for m in AUTH_ERROR_MARKERS)


def utcnow() -> datetime:
    return datetime.now(UTC)


def local_today(tz: ZoneInfo) -> date:
    """Today in the device timezone (overridable in tests)."""
    return datetime.now(tz).date()


def as_utc(dt: datetime) -> datetime:
    # The library returns UTC; treat naive values as UTC.
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def quarter_start(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def prev_quarter(q: date) -> date:
    return quarter_start(q - timedelta(days=1))



# --------------------------------------------------------------------------- transform

def hourly_rows(result) -> list[tuple[datetime, int]]:
    """Merge entries with the same start: when clocks jump forward, the library returns an entry for the
    skipped hour with the start of the following hour."""
    agg: dict[datetime, int] = defaultdict(int)
    for e in result.entries:
        if e.energy is not None:
            agg[as_utc(e.start_date_time)] += int(e.energy)
    return sorted(agg.items())


def period_rows(result, tz: ZoneInfo, monthly: bool = False) -> list[tuple[date, int]]:
    agg: dict[date, int] = defaultdict(int)
    for e in result.entries:
        if e.energy is None:
            continue
        local = as_utc(e.start_date_time).astimezone(tz).date()
        agg[local.replace(day=1) if monthly else local] += int(e.energy)
    return sorted(agg.items())


# --------------------------------------------------------------------------- discovery

@dataclass
class EnergyTarget:
    """One metering point: a plug, or one socket of a power strip."""
    device_id: str
    nickname: str
    model: str
    handler: object
    ip: str | None = None
    mac: str | None = None
    fw_ver: str | None = None
    hw_ver: str | None = None
    parent_id: str | None = None
    position: int | None = None

    @property
    def label(self) -> str:
        return f"{self.nickname} ({self.model}, {self.device_id[-6:]})"


@dataclass
class DiscoveryOutcome:
    parents: dict[str, object]   # device_id -> DiscoveryResult (energy monitoring devices only)
    errors: list[str]
    ignored: list[str]           # devices found without energy monitoring


async def discover(client: ApiClient, addresses: list[str], timeout_s: int) -> DiscoveryOutcome:
    out = DiscoveryOutcome(parents={}, errors=[], ignored=[])
    for addr in addresses:
        try:
            async for maybe in await client.discover_devices(addr, timeout_s=timeout_s):
                try:
                    res = maybe.get()
                except Exception as exc:  # e.g. an auth error of a single device
                    hint = " -> check the Tapo password and Third-Party Compatibility" if is_auth_error(exc) else ""
                    out.errors.append(f"Discovery via {addr}: {exc}{hint}")
                    continue
                if isinstance(res, (DiscoveryResult.PlugEnergyMonitoring, DiscoveryResult.PowerStripEnergyMonitoring)):
                    out.parents.setdefault(res.device_id, res)
                else:
                    out.ignored.append(f"{res.nickname} ({res.model})")
        except Exception as exc:
            out.errors.append(f"Discovery via {addr} fehlgeschlagen: {exc}")
    return out


async def expand_targets(res) -> list[EnergyTarget]:
    info = res.device_info
    ip = res.address[0]
    if isinstance(res, DiscoveryResult.PlugEnergyMonitoring):
        return [EnergyTarget(device_id=res.device_id, nickname=res.nickname, model=res.model, handler=res.handler,
                             ip=ip, mac=info.mac, fw_ver=info.fw_ver, hw_ver=info.hw_ver)]
    # Power strip: energy exists per socket only.
    targets = []
    for child in await res.handler.get_child_device_list():
        targets.append(EnergyTarget(
            device_id=child.device_id, nickname=child.nickname, model=child.model,
            handler=await res.handler.plug_unchecked(child.device_id),
            ip=ip, mac=child.mac, fw_ver=child.fw_ver, hw_ver=child.hw_ver,
            parent_id=res.device_id, position=child.position,
        ))
    return targets


def parent_as_device_row(res) -> EnergyTarget:
    info = res.device_info
    return EnergyTarget(device_id=res.device_id, nickname=res.nickname, model=res.model, handler=None,
                        ip=res.address[0], mac=info.mac, fw_ver=info.fw_ver, hw_ver=info.hw_ver)


# --------------------------------------------------------------------------- fetch

@dataclass
class Window:
    """One get_energy_data request and what came back."""
    kind: str                    # hourly | daily | monthly
    start: date
    end: date
    values: list[int]
    nonzero: int
    first_nonzero: object | None
    last_nonzero: object | None
    suspicious: bool = False
    misdated: str | None = None  # reason when the values do not fit the coarser level


@dataclass
class Fetched:
    tz: ZoneInfo
    hourly: list[tuple[datetime, int]] = field(default_factory=list)
    daily: list[tuple[date, int]] = field(default_factory=list)
    monthly: list[tuple[date, int]] = field(default_factory=list)
    windows: list[Window] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)   # errors: the run becomes partial
    notes: list[str] = field(default_factory=list)      # notes: backfill ended early (expected)


def _looks_replayed(new: list[int], seen: list[list[int]]) -> bool:
    """True when an older window returns exactly the values of a window already fetched. Guards against a
    plug that ignores the requested period and returns its current buffer. Only the common start is compared,
    and it must hold real, varying values; otherwise a plug that was off for a quarter (all zeros) or a constant
    load (always 5 Wh) would count as a replay."""
    for old in seen:
        n = min(len(new), len(old))
        head = new[:n]
        if n >= 3 and head == old[:n] and sum(1 for v in head if v) >= 3 and len(set(head)) > 2:
            return True
    return False


def misdated_reason(rows: list, coarse: dict, group, complete) -> str | None:
    """Checks fine values (hours or days) against the coarser level (days or months) of the same plug.

    On real P110 plugs (FW 1.4.7/1.4.8, checked 2026-11-21) daily windows more than a year back came back
    shifted by about a month. The library warns: "When the method is used beyond its specified capabilities,
    the entries may be dated wrong." Real data satisfies:
      1. sum per group <= coarser value (+1 Wh rounding per entry);
      2. complete groups after the first group with data match (±1 Wh per entry). The first group may be
         smaller, because the plug's memory ends in the middle of it.
    Returns the reason when a window violates this, else None."""
    sums: dict = defaultdict(int)
    counts: dict = defaultdict(int)
    for k, wh in rows:
        g = group(k)
        sums[g] += wh
        counts[g] += 1
    with_data = sorted(g for g, v in sums.items() if v > 0)
    if not with_data:
        return None
    first = with_data[0]
    for g in sorted(sums):
        c = coarse.get(g)
        if c is None:
            continue
        s, tol = sums[g], counts[g]
        if s > c + tol:
            return f"{g}: sum {s} Wh > {c} Wh on the coarser level"
        if g > first and complete(g) and abs(s - c) > tol:
            return f"{g}: sum {s} Wh != {c} Wh on the coarser level"
    return None


async def _window(h, tz, kind: str, start: date, end: date, seen: list[list[int]]):
    interval = {"hourly": EnergyDataInterval.Hourly, "daily": EnergyDataInterval.Daily,
                "monthly": EnergyDataInterval.Monthly}[kind]
    res = await h.get_energy_data(interval, start, end, timezone=tz)
    if kind == "hourly":
        rows = hourly_rows(res)
    else:
        rows = period_rows(res, tz, monthly=(kind == "monthly"))
    values = [wh for _, wh in rows]
    nz = [k for k, wh in rows if wh > 0]
    w = Window(kind, start, end, values, len(nz), nz[0] if nz else None, nz[-1] if nz else None)
    w.suspicious = bool(seen) and _looks_replayed(values, seen)
    seen.append(values)
    return rows, w


def trusted_rows(rows: list, horizon, first_known) -> list:
    """Keep non-zero values always. Keep a 0 only inside the plug's safe memory AND after the device's first
    known measurement (otherwise it is before installation or already discarded)."""
    firsts = [k for k, wh in rows if wh > 0] + ([first_known] if first_known is not None else [])
    if not firsts:
        return []
    start = max(horizon, min(firsts))
    return sorted((k, wh) for k, wh in rows if wh > 0 or k >= start)


async def fetch_energy(t: EnergyTarget, backfill: bool, first_known: dict | None = None) -> Fetched:
    """Normal: 8 days hourly, 2 quarters daily, 2 years monthly (5 requests).
    Backfill: goes further back per interval until BACKFILL_EMPTY_STOP empty windows in a row."""
    h = t.handler
    tz = (await h.get_timezone()).timezone
    today = local_today(tz)
    out = Fetched(tz=tz)
    first_known = first_known or {}
    m_back = today.replace(day=1)
    for _ in range(TRUST_ZERO_MONTHS):
        m_back = (m_back - timedelta(days=1)).replace(day=1)
    horizon = {
        "hourly": datetime.combine(today - timedelta(days=TRUST_ZERO_HOURLY_DAYS), datetime.min.time(), tz)
                  .astimezone(UTC),
        "daily": today - timedelta(days=TRUST_ZERO_DAILY_DAYS),
        "monthly": m_back,
    }

    raw: dict[str, dict] = {"monthly": {}, "daily": {}}  # accepted raw values, reference for the finer level
    this_month = today.replace(day=1)
    validate = {
        # days against months; quarter windows cover whole months, only the current one is open
        "daily": lambda rows: misdated_reason(rows, raw["monthly"], lambda d: d.replace(day=1),
                                              lambda m: m < this_month),
        # hours against days; hourly windows cover whole local days, only today is open
        "hourly": lambda rows: misdated_reason(rows, raw["daily"], lambda ts: ts.astimezone(tz).date(),
                                               lambda d: d < today),
    }

    async def walk(kind: str, windows: list[tuple[date, date]], min_windows: int):
        seen: list[list[int]] = []
        collected: list = []
        empty_streak = 0
        for i, (start, end) in enumerate(windows):
            rows, w = await _window(h, tz, kind, start, end, seen)
            out.windows.append(w)
            if w.suspicious:
                out.warnings.append(f"{t.label}: {kind} {start}..{end} repeats a newer window -> dropped, "
                                    f"{kind} backfill stopped")
                break
            w.misdated = validate[kind](rows) if kind in validate else None
            if w.misdated:
                msg = (f"{t.label}: {kind} {start}..{end} does not fit the coarser level ({w.misdated}) "
                       f"-> misdated, dropped")
                # Older backfill windows: known plug behaviour. Current windows: a real error.
                (out.warnings if i < min_windows else out.notes).append(
                    msg + ("" if i < min_windows else f", {kind} backfill ends here"))
                break
            collected.extend(rows)
            if kind in raw:
                raw[kind].update(rows)
            empty_streak = empty_streak + 1 if w.nonzero == 0 else 0
            if i + 1 >= min_windows and empty_streak >= BACKFILL_EMPTY_STOP:
                break
        getattr(out, kind).extend(trusted_rows(collected, horizon[kind], first_known.get(kind)))

    # Coarse to fine, so every level can be checked against the coarser one.
    # Monthly: Start muss Jahresbeginn sein
    oldest = BACKFILL_OLDEST_YEAR if backfill else today.year - 1
    years = list(range(today.year, oldest - 1, -1))
    await walk("monthly", [(date(y, 1, 1), today if y == today.year else date(y, 12, 31)) for y in years],
               min_windows=2)

    # Daily: Start muss Quartalsbeginn sein
    quarters = [quarter_start(today)]
    for _ in range((BACKFILL_QUARTERS if backfill else 2) - 1):
        quarters.append(prev_quarter(quarters[-1]))
    daily_windows = [(q, today if i == 0 else quarters[i - 1] - timedelta(days=1)) for i, q in enumerate(quarters)]
    await walk("daily", daily_windows, min_windows=2)

    # Hourly: windows of 8 days inclusive (library limit), back to back
    n_hourly = BACKFILL_HOURLY_WINDOWS if backfill else 1
    await walk("hourly", [(today - timedelta(days=7 + 8 * k), today - timedelta(days=8 * k)) for k in range(n_hourly)],
               min_windows=1)
    return out


async def fetch_with_retry(t: EnergyTarget, backfill: bool, first_known: dict | None = None,
                           attempts: int = 2, delay_s: float = 5.0) -> Fetched:
    for attempt in range(1, attempts + 1):
        try:
            return await fetch_energy(t, backfill, first_known)
        except Exception as exc:
            if is_auth_error(exc) or attempt == attempts:
                raise
            log.warning("%s: Versuch %d fehlgeschlagen (%s), neuer Versuch in %.0fs", t.label, attempt, exc, delay_s)
            await asyncio.sleep(delay_s)
    raise RuntimeError("unreachable")


POWER_5MIN_KEEP_DAYS = 10      # how far the plug keeps 5-minute values [measured 2026-11-21: 10 yes, 12 no]
POWER_5MIN_TRUST_DAYS = 9      # trust zeros only while surely inside the plug's memory


async def fetch_power_5min(h, since: datetime | None) -> list[tuple[datetime, int]]:
    """5-minute power since `since` (or as far back as the plug keeps it), in 12 h windows (max. 144 entries)."""
    now = utcnow().replace(second=0, microsecond=0)
    oldest = now - timedelta(days=POWER_5MIN_KEEP_DAYS)
    start = max(oldest, (since - timedelta(minutes=30)) if since else oldest)
    trust = now - timedelta(days=POWER_5MIN_TRUST_DAYS)
    out: dict[datetime, int] = {}
    while start < now:
        end = min(start + timedelta(hours=12), now)
        res = await h.get_power_data(PowerDataInterval.Every5Minutes, start, end)
        for e in res.entries:
            if e.power is None:
                continue
            ts = as_utc(e.start_date_time)
            if e.power > 0 or ts >= trust:
                out[ts] = int(e.power)
        start = end
    return sorted(out.items())


