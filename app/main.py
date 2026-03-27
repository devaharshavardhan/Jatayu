from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.routers import dashboard, api

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="JATAYU Control Plane", version="0.1.0")

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.include_router(dashboard.router)
app.include_router(api.router, prefix="/api")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
