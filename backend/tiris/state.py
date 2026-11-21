"""Process-wide services, created in the app lifespan."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException

from .devices import DeviceService
from .live import LivePoller
from .plugs import PlugPool


@dataclass
class State:
    plugs: PlugPool | None = None
    live: LivePoller | None = None
    devices: DeviceService | None = None
    collecting: bool = False


state = State()


def need_live() -> LivePoller:
    if state.live is None:
        raise HTTPException(503, "live measurement is off (no Tapo account configured)")
    return state.live


def need_devices() -> DeviceService:
    if state.devices is None:
        raise HTTPException(503, "device control is off (no Tapo account configured)")
    return state.devices
