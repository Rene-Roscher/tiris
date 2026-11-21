"""One place that talks to the plugs: a shared client and one logged-in handler per IP.

Live polling, history collection and device control all use the same handlers, so a plug sees one session
instead of three, and a slow login (1.8 s typical, up to 7.7 s measured) happens once.
"""
from __future__ import annotations

import asyncio
import logging

from tapo import ApiClient

from . import history
from .config import Settings

log = logging.getLogger("tiris.plugs")


class PlugPool:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client: ApiClient | None = None
        self._handlers: dict[str, object] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    @property
    def enabled(self) -> bool:
        return self.settings.has_tapo

    def client(self, timeout_s: int = 10) -> ApiClient:
        if self._client is None:
            self._client = ApiClient(self.settings.tapo_username, self.settings.tapo_password, timeout_s=timeout_s)
        return self._client

    async def handler(self, ip: str):
        h = self._handlers.get(ip)
        if h is not None:
            return h
        lock = self._locks.setdefault(ip, asyncio.Lock())
        async with lock:  # several callers asking for a new plug log in once
            h = self._handlers.get(ip)
            if h is None:
                h = await asyncio.wait_for(self.client().p110(ip), 12)
                self._handlers[ip] = h
            return h

    def forget(self, ip: str) -> None:
        """Drop a handler after an error; the next call logs in again."""
        self._handlers.pop(ip, None)

    def adopt(self, ip: str, handler) -> None:
        """Reuse a handler that discovery already logged in."""
        self._handlers[ip] = handler

    async def discover(self, known: dict[str, tuple[str | None, str | None]]) -> history.DiscoveryOutcome:
        """Broadcast and unicast discovery with the wake-up retry for plugs whose local API sleeps (FW 1.4.6+)."""
        s = self.settings
        known_ips = sorted({ip for ip, _ in known.values() if ip and ip not in s.targets})
        addresses = s.targets + known_ips
        outcome = await history.discover(self.client(), addresses, 5)
        missing = [d for d in known if d not in outcome.parents]
        if outcome.errors or missing:
            log.info("%d errors, %d known plugs missing; waiting 20 s for sleeping local APIs, then retrying",
                     len(outcome.errors), len(missing))
            await asyncio.sleep(20)
            retry = await history.discover(self.client(), addresses, 5)
            outcome.parents.update(retry.parents)
            outcome.errors = retry.errors
            outcome.ignored = retry.ignored or outcome.ignored
        return outcome
