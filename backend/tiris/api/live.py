"""Live API: snapshot, recent window, server-sent events."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from ..state import need_live, state

router = APIRouter(prefix="/api/live")


@router.get("")
async def snapshot():
    if state.live is None:
        return {"enabled": False, "devices": {}}
    return {"enabled": True, **state.live.snapshot()}


@router.get("/recent")
async def recent(seconds: int = Query(900, ge=10, le=900)):
    return need_live().recent(seconds)


@router.get("/stream")
async def stream(request: Request):
    live = need_live()
    q = live.subscribe()

    async def events():
        try:
            yield "retry: 3000\n\n"
            yield f"data: {json.dumps(live.snapshot())}\n\n"
            while not await request.is_disconnected():
                try:
                    snap = await asyncio.wait_for(q.get(), 15)
                    yield f"data: {json.dumps(snap)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            live.unsubscribe(q)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
