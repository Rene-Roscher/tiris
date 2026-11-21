"""tiris app: API, collector schedule and live poller in one process."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import analysis, db
from .api import costs as costs_api
from .api import data as data_api
from .api import devices as devices_api
from .api import live as live_api
from .config import settings
from .devices import DeviceService
from .live import LivePoller
from .plugs import PlugPool
from .state import state

log = logging.getLogger("tiris")
SESSION_COOKIE = "tiris_session"
SESSION_DAYS = 30


_SECRET: bytes | None = None


def _secret() -> bytes:
    global _SECRET
    if _SECRET is None:
        _SECRET = _load_secret()
    return _SECRET


def _load_secret() -> bytes:
    s = settings()
    if s.secret_key:
        return s.secret_key.encode()
    with db.pool().connection() as con:   # generated once, kept in the database
        row = con.execute("SELECT value FROM settings WHERE key = 'secret_key'").fetchone()
        if row:
            return row[0].encode()
        key = secrets.token_urlsafe(48)
        con.execute("INSERT INTO settings (key, value) VALUES ('secret_key', %s) ON CONFLICT DO NOTHING",
                    (json.dumps(key),))
        return key.encode()


def _sign(issued: int) -> str:
    mac = hmac.new(_secret(), f"tiris:{issued}".encode(), hashlib.sha256).hexdigest()
    return f"{issued}.{mac}"


def _valid(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    issued, _, _ = token.partition(".")
    if not issued.isdigit() or time.time() - int(issued) > SESSION_DAYS * 86400:
        return False
    return hmac.compare_digest(token, _sign(int(issued)))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = settings()
    if not logging.getLogger("tiris").handlers:   # uvicorn configures the root logger before us
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        logging.getLogger("tiris").addHandler(h)
        logging.getLogger("tiris").propagate = False
    logging.getLogger("tiris").setLevel(logging.INFO)
    applied = db.migrate(s.database_url)
    if applied:
        log.info("migrations applied: %s", ", ".join(applied))
    db.open_pool(s.database_url)
    _apply_retention()
    tasks: list[asyncio.Task] = []
    if s.has_tapo:
        state.plugs = PlugPool(s)
        state.devices = DeviceService(db.pool(), state.plugs)
        state.live = LivePoller(db.pool(), state.plugs, s.live_interval_s)
        state.live.start()
        tasks.append(asyncio.create_task(data_api.scheduler(), name="tiris-collector"))
    else:
        log.warning("no Tapo account configured (TIRIS_TAPO_USERNAME / TIRIS_TAPO_PASSWORD): "
                    "live data, collection and device control are off")
    yield
    for t in tasks:
        t.cancel()
    if state.live:
        await state.live.stop()
    db.close_pool()


def _apply_retention() -> None:
    days = settings().raw_retention_days
    with db.pool().connection() as con:
        con.execute("SELECT remove_retention_policy('power_samples', if_exists => TRUE)")
        if days > 0:
            con.execute("SELECT add_retention_policy('power_samples', make_interval(days => %s))", (days,))


app = FastAPI(title="tiris", docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
              lifespan=lifespan)


@app.middleware("http")
async def auth(request: Request, call_next):
    path = request.url.path
    open_paths = ("/api/health", "/api/auth/login", "/api/auth/status")
    if settings().password and path.startswith("/api/") and path not in open_paths:
        if not _valid(request.cookies.get(SESSION_COOKIE)):
            return JSONResponse({"detail": "login required"}, status_code=401)
    return await call_next(request)


class LoginIn(BaseModel):
    password: str


@app.get("/api/auth/status")
def auth_status(request: Request):
    required = bool(settings().password)
    return {"required": required, "authenticated": not required or _valid(request.cookies.get(SESSION_COOKIE))}


@app.post("/api/auth/login")
async def login(body: LoginIn, response: Response):
    expected = settings().password
    if not expected:
        return {"ok": True}
    if not hmac.compare_digest(body.password.encode(), expected.encode()):
        await asyncio.sleep(0.5)   # slows guessing
        raise HTTPException(401, "wrong password")
    response.set_cookie(SESSION_COOKIE, _sign(int(time.time())), max_age=SESSION_DAYS * 86400, httponly=True,
                        samesite="strict", path="/")
    return {"ok": True}


@app.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


for r in (data_api.router, live_api.router, analysis.router, devices_api.router, costs_api.router):
    app.include_router(r)

_static = Path(settings().static_dir) if settings().static_dir else None
if _static and _static.is_dir():
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        f = (_static / path).resolve()
        if path and f.is_file() and _static.resolve() in f.parents:
            return FileResponse(f)
        return FileResponse(_static / "index.html")


def run() -> None:
    import uvicorn
    s = settings()
    uvicorn.run("tiris.main:app", host=s.host, port=s.port, proxy_headers=True, log_level="info")
