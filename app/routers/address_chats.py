"""Чат адрес–клиент.

REST:
- POST   /api/v1/chats/addresses/{address_id}      — get_or_create чат текущего пользователя.
- GET    /api/v1/chats                             — список моих чатов (client/owner).
- GET    /api/v1/chats/{chat_id}/messages          — история (50 последних).
- POST   /api/v1/chats/{chat_id}/messages          — отправить сообщение.

WebSocket:
- WS     /api/v1/ws/chats/{chat_id}?token=<jwt|cookie>
  - На клиенте: подключение поднимается после открытия чата.
  - При новом сообщении сервер пушит JSON `{type:"message", payload:{...}}`
    всем подключённым (включая отправителя — для эхо).

Push: участникам, которые не подключены к ws, шлём in-app notification +
email-stub (см. services/email_outbox.py).

TODO(moderation): автоматическая фильтрация по словам/контактам — отдельной фазой.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, utcnow
from app.database import AsyncSessionLocal, get_db
from app.enums import AddressPublicationStatus, UserRole
from app.models.address import Address
from app.models.address_chat import AddressChat, AddressChatMessage
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_security import hash_token
from app.services.email_outbox import send_email
from app.services.notification_events import write_user_notification
from app.services.web_push import send_push_to_user

logger = logging.getLogger("address_chats")
router = APIRouter(prefix="/chats", tags=["address-chats"])

MAX_MESSAGE_LENGTH = 2000
HISTORY_LIMIT = 50


# ============================== Schemas ==============================


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    author_user_id: UUID
    body: str
    created_at: datetime


class ChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address_id: UUID
    address_full: str
    provider_name: str
    client_user_id: UUID
    client_email: str
    last_message_at: Optional[datetime]
    created_at: datetime


class ChatMessageCreate(BaseModel):
    body: Annotated[str, Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)]


# ============================== Helpers ==============================


async def _load_chat_with_address(
    db: AsyncSession, chat_id: UUID
) -> tuple[AddressChat, Address]:
    row = (
        await db.execute(
            select(AddressChat, Address)
            .join(Address, Address.id == AddressChat.address_id)
            .where(AddressChat.id == chat_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Чат не найден")
    return row[0], row[1]


def _user_is_chat_participant(user: User, chat: AddressChat, address: Address) -> bool:
    if user.id == chat.client_user_id:
        return True
    if user.role == UserRole.OWNER.value and user.provider_id == address.provider_id:
        return True
    if user.role == UserRole.ADMIN.value:
        return True
    return False


def _build_chat_read(
    chat: AddressChat, address: Address, provider_name: str, client_email: str
) -> ChatRead:
    return ChatRead(
        id=chat.id,
        address_id=address.id,
        address_full=address.full_address,
        provider_name=provider_name,
        client_user_id=chat.client_user_id,
        client_email=client_email,
        last_message_at=chat.last_message_at,
        created_at=chat.created_at,
    )


# ============================== Connection registry =====================


class ChatHub:
    """В памяти: chat_id -> set[(user_id, WebSocket)]."""

    def __init__(self) -> None:
        self._connections: dict[UUID, set[tuple[UUID, WebSocket]]] = {}
        self._lock = asyncio.Lock()

    async def join(self, chat_id: UUID, user_id: UUID, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.setdefault(chat_id, set()).add((user_id, ws))

    async def leave(self, chat_id: UUID, user_id: UUID, ws: WebSocket) -> None:
        async with self._lock:
            bucket = self._connections.get(chat_id)
            if not bucket:
                return
            bucket.discard((user_id, ws))
            if not bucket:
                self._connections.pop(chat_id, None)

    async def connected_user_ids(self, chat_id: UUID) -> set[UUID]:
        async with self._lock:
            return {uid for uid, _ in self._connections.get(chat_id, set())}

    async def broadcast(self, chat_id: UUID, payload: dict) -> None:
        msg = json.dumps(payload, default=str)
        # snapshot subscribers, send outside the lock to avoid blocking new connects
        async with self._lock:
            bucket = list(self._connections.get(chat_id, set()))
        for _uid, ws in bucket:
            try:
                await ws.send_text(msg)
            except Exception:  # noqa: BLE001
                # клиент мог отвалиться — оставим cleanup на disconnect handler
                logger.debug("ws send failed for chat=%s", chat_id, exc_info=True)


hub = ChatHub()


async def _participants_of(
    db: AsyncSession, chat: AddressChat, address: Address
) -> list[User]:
    """Возвращает обоих участников чата: клиента и владельцев адреса.

    Для собственника адреса берём всех активных users с роль OWNER того же провайдера.
    """
    out: list[User] = []
    client = await db.get(User, chat.client_user_id)
    if client is not None:
        out.append(client)
    owners = (
        await db.execute(
            select(User).where(
                User.provider_id == address.provider_id,
                User.role == UserRole.OWNER.value,
                User.is_active.is_(True),
            )
        )
    ).scalars().all()
    out.extend(owners)
    return out


async def _notify_offline(
    db: AsyncSession,
    chat: AddressChat,
    address: Address,
    message: AddressChatMessage,
    author: User,
) -> None:
    """Шлёт email + создаёт in-app уведомление участникам, кто не онлайн в этом чате.

    Запись попадёт в `user_notifications` и появится в шторке уведомлений
    с link → конкретный чат.
    """
    online = await hub.connected_user_ids(chat.id)
    participants = await _participants_of(db, chat, address)
    short_body = (message.body[:140] + "…") if len(message.body) > 140 else message.body
    address_short = address.full_address[:80]
    for user in participants:
        if user.id == author.id or user.id in online:
            continue
        try:
            await write_user_notification(
                db,
                user_id=user.id,
                kind="chat_message",
                title=f"Новое сообщение по адресу {address_short}",
                body=short_body,
                link_type="chat",
                link_id=chat.id,
            )
        except Exception:  # noqa: BLE001
            logger.warning("notif write failed for user=%s", user.id, exc_info=True)
        try:
            await send_email(
                to=user.email,
                subject="Новое сообщение в чате по юридическому адресу",
                body=(
                    f"Адрес: {address.full_address}\n"
                    f"Автор: {author.email}\n\n"
                    f"{message.body}\n\n"
                    "Открыть в личном кабинете."
                ),
            )
        except Exception:  # noqa: BLE001
            logger.warning("email send failed for user=%s", user.id, exc_info=True)
    # commit нотификаций сразу (одна транзакция с message commit'ом уже закрылась)
    try:
        await db.commit()
    except Exception:  # noqa: BLE001
        await db.rollback()

    # Web Push поверх — отдельная попытка (не падаем, если push выключен).
    push_title = f"Сообщение по {address_short}"
    for user in participants:
        if user.id == author.id or user.id in online:
            continue
        try:
            await send_push_to_user(
                db,
                user_id=user.id,
                title=push_title,
                body=short_body,
                url="/",
                tag=f"chat:{chat.id}",
            )
        except Exception:  # noqa: BLE001
            logger.warning("web push failed for user=%s", user.id, exc_info=True)


# ============================== REST endpoints ==============================


@router.post("/addresses/{address_id}", response_model=ChatRead)
async def open_chat_for_address(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatRead:
    # Открывать чат может ТОЛЬКО клиент. Собственник видит входящие чаты в
    # своём кабинете (без явного create). Админ/manager/lawyer — не создают
    # чат под своим логином (это путаница: чат — pair (адрес × клиент)).
    if user.role != UserRole.CLIENT.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Открыть чат с собственником может только клиент",
        )

    # Подгружаем provider сразу — иначе address.provider лениво обратится в
    # БД из async-сессии и упадёт MissingGreenlet'ом.
    address = (
        await db.execute(
            select(Address)
            .options(selectinload(Address.provider))
            .where(Address.id == address_id)
        )
    ).scalar_one_or_none()
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")

    chat = (
        await db.execute(
            select(AddressChat).where(
                AddressChat.address_id == address_id,
                AddressChat.client_user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if chat is None:
        # Новый чат можно создать только по опубликованному и доступному адресу.
        # Иначе клиент мог бы перебором address_id зондировать существование
        # скрытых / снятых с публикации / чужих адресов (информационная разведка).
        # Отдаём 404 как для несуществующего адреса — не подтверждаем сам факт.
        # Уже существующий чат (адрес мог быть снят с публикации позже) — отдаём:
        # клиент не теряет доступ к своей переписке.
        if (
            address.publication_status != AddressPublicationStatus.PUBLISHED.value
            or not address.is_available
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
        chat = AddressChat(address_id=address_id, client_user_id=user.id)
        db.add(chat)
        await db.commit()
        await db.refresh(chat)

    provider_name = address.provider.short_name if address.provider else ""
    return _build_chat_read(chat, address, provider_name, user.email)


@router.get("", response_model=list[ChatRead])
async def list_my_chats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatRead]:
    """Для клиента — его чаты; для собственника — все чаты по адресам организации."""
    stmt = (
        select(AddressChat, Address, User)
        .join(Address, Address.id == AddressChat.address_id)
        .join(User, User.id == AddressChat.client_user_id)
        # selectinload provider — иначе в async-сессии будет MissingGreenlet.
        .options(selectinload(Address.provider))
        .order_by(desc(AddressChat.last_message_at.nullslast()), desc(AddressChat.created_at))
    )
    if user.role == UserRole.CLIENT.value:
        stmt = stmt.where(AddressChat.client_user_id == user.id)
    elif user.role == UserRole.OWNER.value:
        if user.provider_id is None:
            return []
        stmt = stmt.where(Address.provider_id == user.provider_id)
    elif user.role == UserRole.ADMIN.value:
        pass
    else:
        return []

    rows = (await db.execute(stmt)).all()
    result: list[ChatRead] = []
    for chat, address, client in rows:
        provider_name = address.provider.short_name if address.provider else ""
        result.append(_build_chat_read(chat, address, provider_name, client.email))
    return result


@router.get("/{chat_id}/messages", response_model=list[ChatMessageRead])
async def get_chat_messages(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[AddressChatMessage]:
    chat, address = await _load_chat_with_address(db, chat_id)
    if not _user_is_chat_participant(user, chat, address):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к чату")
    # DESC + limit → берём свежие N; затем переворачиваем в ASC чтобы UI рисовал
    # «снизу вверх по времени» без дополнительной сортировки.
    rows = (
        await db.execute(
            select(AddressChatMessage)
            .where(AddressChatMessage.chat_id == chat_id)
            .order_by(desc(AddressChatMessage.created_at))
            .limit(HISTORY_LIMIT)
        )
    ).scalars().all()
    return list(reversed(rows))


@router.post("/{chat_id}/messages", response_model=ChatMessageRead)
async def post_chat_message(
    chat_id: UUID,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AddressChatMessage:
    chat, address = await _load_chat_with_address(db, chat_id)
    if not _user_is_chat_participant(user, chat, address):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к чату")

    body = payload.body.strip()
    if not body:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Пустое сообщение")
    # TODO(moderation): авто-фильтр оскорблений и контактов.

    message = AddressChatMessage(chat_id=chat.id, author_user_id=user.id, body=body)
    db.add(message)
    chat.last_message_at = utcnow()
    await db.commit()
    await db.refresh(message)

    await hub.broadcast(
        chat.id,
        {
            "type": "message",
            "payload": {
                "id": str(message.id),
                "chat_id": str(message.chat_id),
                "author_user_id": str(message.author_user_id),
                "body": message.body,
                "created_at": message.created_at.isoformat(),
            },
        },
    )
    await _notify_offline(db, chat, address, message, user)
    return message


# ============================== WebSocket ==============================


async def _ws_resolve_user(token: str) -> Optional[User]:
    if not token:
        return None
    now = utcnow()
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(UserSession, User)
                .join(User, User.id == UserSession.user_id)
                .where(
                    UserSession.token_hash == hash_token(token),
                    UserSession.revoked_at.is_(None),
                    UserSession.expires_at > now,
                    User.is_active.is_(True),
                )
            )
        ).first()
    return row[1] if row is not None else None


ws_router = APIRouter()


@ws_router.websocket("/ws/chats/{chat_id}")
async def chat_websocket(
    websocket: WebSocket,
    chat_id: UUID,
    token: str = Query(default=""),
) -> None:
    # httponly-cookie не достать из JS, поэтому при same-origin WS-handshake
    # браузер сам прикладывает cookie. Сначала пытаемся cookie, fallback — query.
    from app.config import settings as _settings

    cookie_token = websocket.cookies.get(_settings.session_cookie_name)
    user = await _ws_resolve_user(cookie_token or token)
    if user is None:
        await websocket.close(code=4401)  # custom: unauthorized
        return

    async with AsyncSessionLocal() as db:
        chat = (
            await db.execute(select(AddressChat).where(AddressChat.id == chat_id))
        ).scalar_one_or_none()
        if chat is None:
            await websocket.close(code=4404)
            return
        address = await db.get(Address, chat.address_id)
        if address is None or not _user_is_chat_participant(user, chat, address):
            await websocket.close(code=4403)
            return

    await websocket.accept()
    await hub.join(chat_id, user.id, websocket)
    try:
        while True:
            # Клиентский пинг или сообщение. Мы рассылаем через REST POST, поэтому
            # тут просто держим соединение живым; клиенты могут слать `{"type":"ping"}`.
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        logger.warning("ws loop error chat=%s user=%s", chat_id, user.id, exc_info=True)
    finally:
        await hub.leave(chat_id, user.id, websocket)
