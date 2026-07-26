from __future__ import annotations

"""FastAPI-точка входа."""
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select

from app.api_errors import register_error_handlers
from app.auth import utcnow
from app.config import settings
from app.services.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    csrf_check_required,
    set_csrf_cookie,
    tokens_match,
)
from app.database import AsyncSessionLocal
from app.models.user import User
from app.models.user_session import UserSession
from app.routers import (
    address_chats,
    address_moderation,
    address_photos,
    address_reviews,
    address_services,
    addresses,
    application_documents,
    applications,
    auth,
    client_dashboard,
    clients,
    demo,
    egrn,
    marketplace,
    mobile_auth,
    notifications,
    owner_dashboard,
    payments,
    provider_requests,
    providers,
    push,
    registry,
    templates,
    webhooks,
    workflow,
)

app = FastAPI(
    title="Legal Address Service API",
    version="1.0.0",
    description=(
        "Сервис выдачи юридических адресов: маркетплейс, заявки клиентов, документы.\n\n"
        "**Стабильный публичный API:** `/api/v1/...` — версионируем при ломающих изменениях.\n\n"
        "**Формат ошибок:** `{\"error\": {\"code\": \"<slug>\", \"message\": \"...\", \"details\": ...}}`\n\n"
        "**Аутентификация:**\n"
        "- Web: cookie `legal_address_session` (HttpOnly) + refresh cookie на `/api/v1/auth/refresh`.\n"
        "- Mobile / сторонние интеграции: `Authorization: Bearer <access_token>` из `/api/v1/mobile/auth/login`.\n\n"
        "**Webhooks:** outbound события доставляются на зарегистрированные подписки с HMAC-SHA256 подписью."
    ),
    openapi_tags=[
        {"name": "auth", "description": "Регистрация/логин/сессии для web и публичных форм."},
        {"name": "mobile-auth", "description": "Bearer-токены для нативных клиентов и интеграций."},
        {"name": "marketplace", "description": "Публичный каталог адресов и приём заявок без авторизации."},
        {"name": "webhooks", "description": "Подписки на события и входящие webhooks (платежи и т.п.)."},
        {"name": "meta", "description": "Служебные ручки: liveness, readiness."},
    ],
)
register_error_handlers(app)


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


API_PREFIX = "/api/v1"


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
        f"{API_PREFIX}/auth/login",
        f"{API_PREFIX}/auth/refresh",
        f"{API_PREFIX}/auth/bootstrap-admin",
        f"{API_PREFIX}/auth/bootstrap-state",
        f"{API_PREFIX}/mobile/auth/login",
        f"{API_PREFIX}/mobile/auth/refresh",
    }
    if path in public_exact:
        return True
    if path.startswith("/assets/"):
        return True
    if path.startswith("/invite/"):
        return True
    # Публичны ТОЛЬКО конкретные inbound-приёмники платежей. Админ-CRUD подписок
    # (/webhooks/subscriptions*) обязан идти через auth-middleware → require_admin.
    if path.startswith(f"{API_PREFIX}/webhooks/payments/"):
        return True
    if path in {
        f"{API_PREFIX}/webhooks/cdek_pay/payment",
        f"{API_PREFIX}/webhooks/cdek_pay/refund",
    }:
        return True
    if path == f"{API_PREFIX}/marketplace/addresses" and method == "GET":
        return True
    if path == f"{API_PREFIX}/marketplace/addresses/search" and method == "GET":
        return True
    if path == f"{API_PREFIX}/marketplace/fns-options" and method == "GET":
        return True
    if path == f"{API_PREFIX}/marketplace/geo" and method == "GET":
        return True
    # Одна карточка каталога по прямой ссылке: /marketplace/addresses/{id}.
    # Ровно один сегмент после addresses/ — вложенные пути (photos, services,
    # chats) сюда не попадают и остаются под авторизацией.
    if (
        path.startswith(f"{API_PREFIX}/marketplace/addresses/")
        and method == "GET"
        and "/" not in path[len(f"{API_PREFIX}/marketplace/addresses/"):]
    ):
        return True
    # Публичная лента отзывов по адресу: /marketplace/addresses/{id}/reviews
    if (
        path.startswith(f"{API_PREFIX}/marketplace/addresses/")
        and path.endswith("/reviews")
        and method == "GET"
    ):
        return True
    if path == f"{API_PREFIX}/push/public-key" and method == "GET":
        return True
    if path == f"{API_PREFIX}/marketplace/provider-requests" and method == "POST":
        return True
    if path == f"{API_PREFIX}/marketplace/applications" and method == "POST":
        return True
    # Сами фото отдаются роутером: approved -> публично, остальные -> auth-check внутри.
    if (
        path.startswith(f"{API_PREFIX}/address-photos/")
        and path.endswith("/raw")
        and method == "GET"
    ):
        return True
    return (
        path.startswith(f"{API_PREFIX}/auth/invitations/") and path.endswith("/accept")
    )


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if _is_public_path(request.url.path, request.method):
        return await call_next(request)

    # Куку браузер подставляет сам — значит запрос может быть подделан с чужого
    # сайта. Bearer-токен так не подставляется, поэтому CSRF-проверка нужна
    # только для куки-авторизации.
    authenticated_by_cookie = settings.session_cookie_name in request.cookies
    if csrf_check_required(
        method=request.method, authenticated_by_cookie=authenticated_by_cookie
    ) and not tokens_match(
        request.cookies.get(CSRF_COOKIE_NAME),
        request.headers.get(CSRF_HEADER_NAME),
    ):
        return JSONResponse(
            {
                "error": {
                    "code": "csrf_failed",
                    "message": "Проверка CSRF не пройдена. Обновите страницу и повторите.",
                }
            },
            status_code=403,
        )

    token = _session_token_from_request(request)
    if not token:
        return JSONResponse(
            {"error": {"code": "unauthorized", "message": "Требуется вход"}},
            status_code=401,
        )

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
            return JSONResponse(
                {"error": {"code": "unauthorized", "message": "Сессия истекла. Войдите заново"}},
                status_code=401,
            )

        session, user = row
        request.state.user_id = user.id
        request.state.user_role = user.role
        request.state.user_email = user.email
        request.state.session_id = session.id

        from app.services.auth_sessions import should_update_last_seen

        if should_update_last_seen(session, now):
            session.last_seen_at = now
            await db.commit()

    response = await call_next(request)
    # Досеиваем токен уже существующим сессиям: после выката пользователи
    # остаются залогинены, но CSRF-куки у них ещё нет, и первый же POST
    # упёрся бы в 403. Первый GET (обычно /auth/me на загрузке SPA) её выдаёт.
    if authenticated_by_cookie and CSRF_COOKIE_NAME not in request.cookies:
        set_csrf_cookie(response)
    return response


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


api_v1 = APIRouter(prefix=API_PREFIX)
api_v1.include_router(auth.router)
api_v1.include_router(mobile_auth.router)
api_v1.include_router(marketplace.router)
api_v1.include_router(notifications.router)
api_v1.include_router(client_dashboard.router)
api_v1.include_router(owner_dashboard.router)
api_v1.include_router(workflow.router)
api_v1.include_router(application_documents.router)
api_v1.include_router(address_photos.router)
api_v1.include_router(providers.router)
api_v1.include_router(push.router)
api_v1.include_router(provider_requests.router)
api_v1.include_router(addresses.router)
api_v1.include_router(address_moderation.router)
api_v1.include_router(address_moderation.admin_router)
api_v1.include_router(address_services.router)
api_v1.include_router(address_services.owner_router)
api_v1.include_router(address_reviews.router)
api_v1.include_router(address_reviews.admin_router)
api_v1.include_router(address_chats.router)
# WebSocket-роут отдельно — middleware пропускает по public-path рулу ниже.
api_v1.include_router(address_chats.ws_router)
api_v1.include_router(egrn.router)
api_v1.include_router(clients.router)
api_v1.include_router(applications.router)
api_v1.include_router(registry.router)
api_v1.include_router(templates.router)
# Демо-сид создаёт аккаунты (в т.ч. admin) с известным паролем — только вне прода.
if settings.app_env != "production":
    api_v1.include_router(demo.router)
api_v1.include_router(webhooks.router)
api_v1.include_router(payments.router)
app.include_router(api_v1)


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
