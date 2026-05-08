from __future__ import annotations

"""FastAPI-точка входа. Маршруты — стабы (501), цель — фиксация контракта API."""
from fastapi import FastAPI

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

app.include_router(providers.router)
app.include_router(addresses.router)
app.include_router(egrn.router)
app.include_router(clients.router)
app.include_router(applications.router)
app.include_router(templates.router)


@app.get("/health", tags=["meta"], summary="Liveness probe")
async def health() -> dict[str, str]:
    return {"status": "ok"}
