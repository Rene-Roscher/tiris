"""Live polling: every plug every `live_interval_s` (default 2 s) via get_energy_meter_data.

- Raw samples go to power_samples in batches; Timescale aggregates them to 1 min / 15 min / 1 h.
- Energy per sample is the delta of the plug's mWh counter, so energy is exact whatever the poll rate.
  After a gap longer than MAX_GAP_S, or when the counter goes backwards (plug restarted), the delta is 0:
  that energy is covered by the hourly history and the 5-minute buffer instead of landing in one sample.
- The last 15 minutes stay in memory for the live view; subscribers (SSE) get a snapshot every tick.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from datetime import UTC, datetime

from psycopg_pool import ConnectionPool

from .plugs import PlugPool

log = logging.getLogger("tiris.live")

BUFFER_S = 15 * 60
MAX_GAP_S = 300
FLUSH_EVERY_S = 10
REQUEST_TIMEOUT_S = 2.5
STALE_S = 10


class LivePoller:
    def __init__(self, db: ConnectionPool, plugs: PlugPool, interval_s: float):
        self.db, self.plugs, self.interval = db, plugs, interval_s
        self.devices: list[tuple[str, str]] = []           # (device_id, ip)
        self.latest: dict[str, dict] = {}
        self.history: dict[str, deque] = {}
        self.total_history: deque = deque(maxlen=int(BUFFER_S / interval_s) + 10)
        self._last_energy: dict[str, tuple[float, int]] = {}   # device -> (unix ts, energy_mwh)
        self._pending: list[tuple] = []
        self._subs: set[asyncio.Queue] = set()
        self._task: asyncio.Task | None = None
        self._last_flush = time.monotonic()
        self.errors: dict[str, str] = {}
        self._reload = True

    def reload_devices(self) -> None:
        """Called after a collection run, which may have found new plugs or new IPs."""
        self._reload = True

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._load_last_energy()
        self._task = asyncio.create_task(self._run(), name="tiris-live")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await asyncio.to_thread(self._flush)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subs.discard(q)

    # ------------------------------------------------------------------ polling
    def _load_devices(self) -> None:
        with self.db.connection() as con:
            self.devices = con.execute(
                "SELECT device_id, ip FROM devices WHERE NOT retired AND ip IS NOT NULL AND parent_id IS NULL "
                "ORDER BY device_id").fetchall()

    def _load_last_energy(self) -> None:
        """Continue the counter deltas across a restart of tiris (short restarts lose no energy)."""
        try:
            with self.db.connection() as con:
                rows = con.execute(
                    "SELECT DISTINCT ON (device_id) device_id, ts, energy_mwh FROM power_samples "
                    "WHERE ts > now() - make_interval(secs => %s) AND energy_mwh IS NOT NULL "
                    "ORDER BY device_id, ts DESC", (MAX_GAP_S,)).fetchall()
            self._last_energy = {d: (ts.timestamp(), e) for d, ts, e in rows}
        except Exception as exc:
            log.warning("last energy counters not loaded: %s", exc)

    async def _run(self) -> None:
        last_dev_load = 0.0
        while True:
            tick = time.monotonic()
            try:
                if self._reload or tick - last_dev_load > 60 or not self.devices:
                    self._reload = False
                    await asyncio.to_thread(self._load_devices)
                    last_dev_load = tick
                await self._poll_once()
                if time.monotonic() - self._last_flush >= FLUSH_EVERY_S:
                    batch, self._pending = self._pending, []
                    self._last_flush = time.monotonic()
                    asyncio.create_task(asyncio.to_thread(self._write, batch))
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("live poll failed")
            await asyncio.sleep(max(0.05, self.interval - (time.monotonic() - tick)))

    async def _read(self, did: str, ip: str) -> dict | None:
        try:
            h = await self.plugs.handler(ip)
            m = await asyncio.wait_for(h.get_energy_meter_data(), REQUEST_TIMEOUT_S)
            self.errors.pop(did, None)
            w, v, a = m.power_mw / 1000, m.voltage_mv / 1000, m.current_ma / 1000
            pf = w / (v * a) if v > 0 and a > 0.02 else None
            return {"w": round(w, 2), "v": round(v, 1), "a": round(a, 3),
                    "pf": round(min(pf, 1.0), 2) if pf else None, "energy_mwh": m.energy_mwh}
        except Exception as exc:
            if did not in self.errors:
                log.info("%s (%s): %s", did[-6:], ip, exc)
            self.errors[did] = str(exc)[:200]
            self.plugs.forget(ip)
            return None

    async def _poll_once(self) -> None:
        results = await asyncio.gather(*(self._read(did, ip) for did, ip in self.devices))
        now = time.time()
        ts = datetime.fromtimestamp(now, UTC)
        for (did, _), r in zip(self.devices, results, strict=True):
            if r is None:
                continue
            prev = self._last_energy.get(did)
            delta = 0
            if prev and now - prev[0] <= MAX_GAP_S and r["energy_mwh"] >= prev[1]:
                delta = r["energy_mwh"] - prev[1]
            self._last_energy[did] = (now, r["energy_mwh"])
            r["at"] = now
            self.latest[did] = r
            self.history.setdefault(did, deque(maxlen=self.total_history.maxlen)).append((round(now, 1), r["w"]))
            self._pending.append((did, ts, r["w"], r["v"], r["a"], r["energy_mwh"], delta))
        total = sum(r["w"] for r in self.latest.values() if now - r["at"] < STALE_S)
        if any(r is not None for r in results):
            self.total_history.append((round(now, 1), round(total, 2)))
        snap = self.snapshot()
        for q in list(self._subs):
            if q.full():
                q.get_nowait()
            q.put_nowait(snap)

    def _write(self, batch: list[tuple]) -> None:
        if not batch:
            return
        try:
            with self.db.connection() as con, con.cursor().copy(
                    "COPY power_samples (device_id, ts, w, v, a, energy_mwh, delta_mwh) FROM STDIN") as cp:
                for row in batch:
                    cp.write_row(row)
        except Exception as exc:
            log.warning("%d live samples not stored: %s", len(batch), exc)

    def _flush(self) -> None:
        batch, self._pending = self._pending, []
        self._write(batch)

    # ------------------------------------------------------------------ views
    def snapshot(self) -> dict:
        now = time.time()
        devs = {did: {k: v for k, v in r.items() if k != "at"} | {"age": round(now - r["at"], 1)}
                for did, r in self.latest.items() if now - r["at"] < 60}
        fresh = [d for d in devs.values() if d["age"] < STALE_S]
        return {"at": now, "total_w": round(sum(d["w"] for d in fresh), 2), "online": len(fresh),
                "known": len(self.devices), "interval_s": self.interval, "devices": devs}

    def recent(self, seconds: int = BUFFER_S) -> dict:
        cut = time.time() - seconds
        return {"interval_s": self.interval,
                "total": [p for p in self.total_history if p[0] >= cut],
                "devices": {d: [p for p in h if p[0] >= cut] for d, h in self.history.items()}}
