from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services import dataset_service

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    scenarios = dataset_service.list_scenarios()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"request": request, "scenarios": scenarios},
    )
