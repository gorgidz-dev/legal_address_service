from __future__ import annotations

"""FastAPI-точка входа."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.auth import utcnow
from app.config import settings
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.user_session import UserSession
from app.routers import (
    addresses,
    applications,
    auth,
    client_dashboard,
    clients,
    egrn,
    marketplace,
    mobile_auth,
    owner_dashboard,
    providers,
    registry,
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


def _session_token_from_request(request: Request) -> str | None:
    cookie_token = request.cookies.get(settings.session_cookie_name)
    if cookie_token:
        return cookie_token

    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _is_public_path(path: str, method: str) -> bool:
    if method == "OPTIONS":
        return True
    public_exact = {
        "/",
        "/health",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/favicon.ico",
        "/auth/login",
        "/auth/bootstrap-admin",
        "/auth/bootstrap-state",
        "/mobile/auth/login",
    }
    if path in public_exact:
        return True
    if path.startswith("/assets/"):
        return True
    if path.startswith("/invite/"):
        return True
    if path == "/marketplace/addresses" and method == "GET":
        return True
    if path == "/marketplace/provider-requests" and method == "POST":
        return True
    if path == "/marketplace/applications" and method == "POST":
        return True
    return path.startswith("/auth/invitations/") and path.endswith("/accept")


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if _is_public_path(request.url.path, request.method):
        return await call_next(request)

    token = _session_token_from_request(request)
    if not token:
        return JSONResponse({"detail": "Требуется вход"}, status_code=401)

    from app.services.auth_security import hash_token

    now = utcnow()
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserSession, User)
            .join(User, User.id == UserSession.user_id)
            .where(
                UserSession.token_hash == hash_token(token),
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
                User.is_active.is_(True),
            )
        )
        row = result.first()
        if row is None:
            return JSONResponse({"detail": "Сессия истекла. Войдите заново"}, status_code=401)

        session, user = row
        request.state.user_id = user.id
        request.state.user_role = user.role
        request.state.user_email = user.email
        request.state.session_id = session.id

    return await call_next(request)


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


app.include_router(auth.router)
app.include_router(mobile_auth.router)
app.include_router(marketplace.router)
app.include_router(client_dashboard.router)
app.include_router(owner_dashboard.router)
app.include_router(providers.router)
app.include_router(addresses.router)
app.include_router(egrn.router)
app.include_router(clients.router)
app.include_router(applications.router)
app.include_router(registry.router)
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


@app.get("/invite/{token}", include_in_schema=False)
async def frontend_invite(token: str) -> FileResponse:
    index_path = FRONTEND_DIST / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return FileResponse(PROJECT_ROOT / "README.md", media_type="text/plain")
