from __future__ import annotations

"""FastAPI-точка входа."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import (
    addresses,
    applications,
    clients,
    egrn,
    providers,
    templates,
)

app = FastAPI(
    title="Legal Address Service API",
    version="0.1.0",
    description=(
        "Сервис выдачи договоров и гарантийных писем на юридический адрес.\n\n"
        "Исполнитель — ИП. Заказчик — ЮЛ. Заявка имеет два типа:\n"
        "- `initial_registration` — выдаём только гарантийку, ЮЛ ещё не существует.\n"
        "- `address_change` — выдаём договор + гарантийку для существующего ЮЛ."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(providers.router)
app.include_router(addresses.router)
app.include_router(egrn.router)
app.include_router(clients.router)
app.include_router(applications.router)
app.include_router(templates.router)


@app.get("/health", tags=["meta"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/", include_in_schema=False)
async def frontend_index() -> FileResponse:
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return FileResponse(PROJECT_ROOT / "README.md", media_type="text/plain")
