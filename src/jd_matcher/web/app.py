"""
FastAPI application factory (C8 — Web UI: backend).

Server-rendered HTML via Jinja2; HTMX-compatible fragment endpoints.
Bind to 127.0.0.1 only (never 0.0.0.0).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from jd_matcher.web.routes import router

_TEMPLATES_DIR = Path(__file__).parent / "templates"
_STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="jd-matcher", version="0.1.0", docs_url=None, redoc_url=None)

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
app.include_router(router)
