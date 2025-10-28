"""Entrypoint for the Heimdex API service."""

from __future__ import annotations

import os
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from . import SERVICE_NAME, __version__
from .logger import log_event

_ENV = os.getenv("HEIMDEX_ENV", "local")
_STARTED_AT = datetime.now(UTC)
_STARTED_AT_ISO = _STARTED_AT.isoformat()

app = FastAPI(title="Heimdex API", version=__version__)


@app.on_event("startup")
async def on_startup() -> None:
    log_event("INFO", "starting", env=_ENV, started_at=_STARTED_AT_ISO)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    log_event("INFO", "stopping")


@app.middleware("http")
async def request_logger(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    log_event(
        "INFO",
        "request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


@app.get("/healthz", response_class=JSONResponse)
async def healthz() -> JSONResponse:
    payload = {
        "ok": True,
        "service": SERVICE_NAME,
        "version": __version__,
        "env": _ENV,
        "started_at": _STARTED_AT_ISO,
    }
    return JSONResponse(content=payload)
