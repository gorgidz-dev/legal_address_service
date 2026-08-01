"""Переписка по адресу: клиент, собственник и площадка в одной ветке.

REST:
- POST   /api/v1/chats/addresses/{address_id}        — клиент открывает ветку по адресу.
- POST   /api/v1/chats/applications/{application_id} — ветка по заявке (любой участник).
- GET    /api/v1/chats                               — мои ветки + счётчик непрочитанного.
- GET    /api/v1/chats/{chat_id}/messages            — история (50 последних).
- POST   /api/v1/chats/{chat_id}/messages            — текстовое сообщение.
- POST   /api/v1/chats/{chat_id}/messages/upload     — сообщение с файлами (multipart).
- GET    /api/v1/chats/{chat_id}/attachments/{id}/download — скачать вложение.
- POST   /api/v1/chats/{chat_id}/read                — отметить прочитанным.

WebSocket:
- WS     /api/v1/ws/chats/{chat_id}
  Аутентификация только по HttpOnly session-cookie: токен в query-параметре
  утекает в логи прокси, в историю браузера и в Referer.

Кто участник и как подписано сообщение — services/chat_threads.py. Что можно
приложить — services/chat_attachments.py. Здесь только транспорт.

TODO(moderation): автоматическая фильтрация по словам/контактам — отдельной фазой.
"""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user, utcnow
from app.database import AsyncSessionLocal, get_db
from app.enums import AddressPublicationStatus, UserRole
from app.models.address import Address
from app.models.address_chat import AddressChat, AddressChatMessage
from app.models.application import Application
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_security import hash_token
from app.services.chat_attachments import (
    attach_file,
    attachment_download_url,
    attachments_for_messages,
    content_type_for,
    ensure_message_has_content,
    ensure_within_limits,
    load_attachment,
)
from app.services.chat_threads import (
    author_side,
    display_name,
    ensure_application_access,
    ensure_participant,
    is_participant,
    is_staff,
    mark_read,
    participants_for_notice,
    resolve_thread_for_application,
    unread_counts,
)
from app.services.email_outbox import send_email
from app.services.notification_events import write_user_notification
from app.services.storage import local_stored_file_path, read_stored_file_async
from app.services.web_push import send_push_to_user

logger = logging.getLogger("address_chats")
router = APIRouter(prefix="/chats", tags=["address-chats"])

MAX_MESSAGE_LENGTH = 2000
HISTORY_LIMIT = 50


# ============================== Schemas ==============================


class ChatAttachmentRead(BaseModel):
    id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    download_url: str


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    chat_id: UUID
    author_user_id: UUID
    #: client | owner | staff — чья это реплика. Без него площадка в интерфейсе
    #: выглядела бы собственником: раньше «всё, что не клиент» подписывалось им.
    author_side: str
    author_name: str
    body: str
    created_at: datetime
    attachments: list[ChatAttachmentRead] = []


class ChatRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    address_id: UUID
    address_full: str
    provider_name: str
    client_user_id: UUID
    client_email: str
    client_name: str
    last_message_at: Optional[datetime]
    created_at: datetime
    unread_count: int = 0


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


def _build_chat_read(
    chat: AddressChat,
    address: Address,
    provider_name: str,
    client: User | None,
    unread: int = 0,
) -> ChatRead:
    return ChatRead(
        id=chat.id,
        address_id=address.id,
        address_full=address.full_address,
        provider_name=provider_name,
        client_user_id=chat.client_user_id,
        client_email=getattr(client, "email", "") or "",
        client_name=getattr(client, "full_name", "") or getattr(client, "email", "") or "",
        last_message_at=chat.last_message_at,
        created_at=chat.created_at,
        unread_count=unread,
    )


def _message_read(
    message: AddressChatMessage,
    *,
    author: User | None,
    viewer: object,
    provider_name: str,
    attachments: list[ChatAttachmentRead],
) -> ChatMessageRead:
    return ChatMessageRead(
        id=message.id,
        chat_id=message.chat_id,
        author_user_id=message.author_user_id,
        author_side=author_side(author) if author is not None else "client",
        author_name=(
            display_name(author, viewer=viewer, provider_name=provider_name)
            if author is not None
            else "Участник"
        ),
        body=message.body,
        created_at=message.created_at,
        attachments=attachments,
    )


async def _provider_name_for(db: AsyncSession, address: Address) -> str:
    """Название организации собственника — им подписаны его реплики.

    Отдельным запросом с selectinload: address сюда приходит из разных мест, и
    ленивое обращение к .provider в async-сессии падает MissingGreenlet'ом.
    """
    loaded = (
        await db.execute(
            select(Address)
            .options(selectinload(Address.provider))
            .where(Address.id == address.id)
        )
    ).scalar_one_or_none()
    if loaded is None or loaded.provider is None:
        return ""
    return loaded.provider.short_name


async def _attachment_reads(
    db: AsyncSession, chat_id: UUID, message_ids: list[UUID]
) -> dict[UUID, list[ChatAttachmentRead]]:
    grouped = await attachments_for_messages(db, message_ids)
    return {
        message_id: [
            ChatAttachmentRead(
                id=attachment.id,
                original_filename=file_record.original_filename,
                content_type=file_record.content_type,
                size_bytes=file_record.size_bytes,
                download_url=attachment_download_url(chat_id, attachment.id),
            )
            for attachment, file_record in items
        ]
        for message_id, items in grouped.items()
    }


# ============================== Connection registry =====================


@dataclass(frozen=True)
class _Connection:
    user_id: UUID
    staff: bool
    ws: WebSocket


class ChatHub:
    """В памяти: chat_id -> подключения.

    Реестр живёт в процессе. При нескольких воркерах сообщение увидят только
    те, кто попал на тот же процесс; остальные получат его при перезагрузке
    истории и по уведомлению. Сейчас backend запускается одним процессом —
    если это изменится, реестр придётся вынести в Redis.
    """

    def __init__(self) -> None:
        self._connections: dict[UUID, list[_Connection]] = {}
        self._lock = asyncio.Lock()

    async def join(self, chat_id: UUID, user_id: UUID, ws: WebSocket, *, staff: bool) -> None:
        async with self._lock:
            self._connections.setdefault(chat_id, []).append(
                _Connection(user_id=user_id, staff=staff, ws=ws)
            )

    async def leave(self, chat_id: UUID, user_id: UUID, ws: WebSocket) -> None:
        async with self._lock:
            bucket = self._connections.get(chat_id)
            if not bucket:
                return
            self._connections[chat_id] = [c for c in bucket if c.ws is not ws]
            if not self._connections[chat_id]:
                self._connections.pop(chat_id, None)

    async def connected_user_ids(self, chat_id: UUID) -> set[UUID]:
        async with self._lock:
            return {c.user_id for c in self._connections.get(chat_id, [])}

    async def broadcast(
        self, chat_id: UUID, *, for_staff: dict, for_others: dict
    ) -> None:
        """Две версии одного события.

        Подпись автора зависит от читателя: коллеге видно, кто из операторов
        ответил, клиенту и собственнику — «Площадка». Одна общая рассылка либо
        раскрыла бы имя оператора всем, либо скрыла бы его от своих.
        """
        staff_msg = json.dumps(for_staff, default=str)
        others_msg = json.dumps(for_others, default=str)
        async with self._lock:
            bucket = list(self._connections.get(chat_id, []))
        for connection in bucket:
            try:
                await connection.ws.send_text(staff_msg if connection.staff else others_msg)
            except Exception:  # noqa: BLE001
                # клиент мог отвалиться — оставим cleanup на disconnect handler
                logger.debug("ws send failed for chat=%s", chat_id, exc_info=True)


hub = ChatHub()


async def _notify_offline(
    db: AsyncSession,
    chat: AddressChat,
    address: Address,
    message: AddressChatMessage,
    author: User,
    *,
    attachment_names: list[str],
) -> None:
    """Уведомляет участников, которых нет онлайн в этой ветке.

    Площадка здесь наравне с клиентом и собственником: администрация — участник
    переписки, а не наблюдатель, который заметит сообщение, когда зайдёт сам.
    """
    online = await hub.connected_user_ids(chat.id)
    participants = await participants_for_notice(db, chat, address)
    if message.body.strip():
        short_body = (message.body[:140] + "…") if len(message.body) > 140 else message.body
    elif attachment_names:
        short_body = "Файл: " + ", ".join(attachment_names[:3])
    else:
        short_body = "Новое сообщение"
    if message.body.strip() and attachment_names:
        short_body = f"{short_body} (+{len(attachment_names)} файл.)"
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
                    f"{message.body or short_body}\n\n"
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
                # «/» — публичная главная, поэтому ведём сразу в чаты кабинета:
                # раздел один и тот же у клиента, собственника и админа.
                url="/app/chats",
                tag=f"chat:{chat.id}",
            )
        except Exception:  # noqa: BLE001
            logger.warning("web push failed for user=%s", user.id, exc_info=True)


async def _publish(
    db: AsyncSession,
    *,
    chat: AddressChat,
    address: Address,
    message: AddressChatMessage,
    author: User,
    attachments: list[ChatAttachmentRead],
    provider_name: str,
) -> ChatMessageRead:
    """Разослать сообщение в сокеты и уведомления, вернуть его автору."""
    staff_view = _message_read(
        message,
        author=author,
        viewer=_StaffViewer(),
        provider_name=provider_name,
        attachments=attachments,
    )
    outsider_view = _message_read(
        message,
        author=author,
        viewer=_OutsiderViewer(),
        provider_name=provider_name,
        attachments=attachments,
    )
    await hub.broadcast(
        chat.id,
        for_staff={"type": "message", "payload": json.loads(staff_view.model_dump_json())},
        for_others={"type": "message", "payload": json.loads(outsider_view.model_dump_json())},
    )
    await _notify_offline(
        db,
        chat,
        address,
        message,
        author,
        attachment_names=[item.original_filename for item in attachments],
    )
    return staff_view if is_staff(author) else outsider_view


class _StaffViewer:
    role = UserRole.ADMIN.value


class _OutsiderViewer:
    role = UserRole.CLIENT.value


# ============================== REST endpoints ==============================


@router.post("/addresses/{address_id}", response_model=ChatRead)
async def open_chat_for_address(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatRead:
    # Открывать ветку по объявлению может ТОЛЬКО клиент. Собственник видит
    # входящие в своём кабинете, площадка — через заявку или список чатов.
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
    return _build_chat_read(chat, address, provider_name, user)


@router.post("/applications/{application_id}", response_model=ChatRead)
async def open_chat_for_application(
    application_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatRead:
    """Ветка переписки по заявке — одна и та же для всех троих.

    Раньше из карточки заявки чат открывался только у клиента: ручка требовала
    роль client, и собственник с оператором упирались в 403. Здесь ветку
    получает любой участник — это и есть «вся переписка в одном месте».
    """
    application = await db.get(Application, application_id)
    if application is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заявка не найдена")
    ensure_application_access(user, application)

    address = (
        await db.execute(
            select(Address)
            .options(selectinload(Address.provider))
            .where(Address.id == application.address_id)
        )
    ).scalar_one_or_none()
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес заявки не найден")

    chat = await resolve_thread_for_application(db, application)
    await db.commit()
    await db.refresh(chat)

    client = await db.get(User, chat.client_user_id)
    unread = await unread_counts(db, chat_ids=[chat.id], user_id=user.id)
    provider_name = address.provider.short_name if address.provider else ""
    return _build_chat_read(chat, address, provider_name, client, unread.get(chat.id, 0))


@router.get("", response_model=list[ChatRead])
async def list_my_chats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatRead]:
    """Клиенту — его ветки, собственнику — по адресам организации, площадке — все."""
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
    elif not is_staff(user):
        return []

    rows = (await db.execute(stmt)).all()
    unread = await unread_counts(
        db, chat_ids=[chat.id for chat, _address, _client in rows], user_id=user.id
    )
    result: list[ChatRead] = []
    for chat, address, client in rows:
        provider_name = address.provider.short_name if address.provider else ""
        result.append(
            _build_chat_read(chat, address, provider_name, client, unread.get(chat.id, 0))
        )
    return result


@router.get("/{chat_id}/messages", response_model=list[ChatMessageRead])
async def get_chat_messages(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ChatMessageRead]:
    chat, address = await _load_chat_with_address(db, chat_id)
    ensure_participant(user, chat, address)
    # DESC + limit → берём свежие N; затем переворачиваем в ASC чтобы UI рисовал
    # «снизу вверх по времени» без дополнительной сортировки.
    rows = (
        await db.execute(
            select(AddressChatMessage, User)
            .join(User, User.id == AddressChatMessage.author_user_id)
            .where(AddressChatMessage.chat_id == chat_id)
            .order_by(desc(AddressChatMessage.created_at))
            .limit(HISTORY_LIMIT)
        )
    ).all()
    rows = list(reversed(rows))

    attachments = await _attachment_reads(
        db, chat_id, [message.id for message, _author in rows]
    )
    provider_name = await _provider_name_for(db, address)

    return [
        _message_read(
            message,
            author=author,
            viewer=user,
            provider_name=provider_name,
            attachments=attachments.get(message.id, []),
        )
        for message, author in rows
    ]


@router.post("/{chat_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_chat_read(
    chat_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    chat, address = await _load_chat_with_address(db, chat_id)
    ensure_participant(user, chat, address)
    await mark_read(db, chat_id=chat.id, user_id=user.id, when=utcnow())
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{chat_id}/messages", response_model=ChatMessageRead)
async def post_chat_message(
    chat_id: UUID,
    payload: ChatMessageCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatMessageRead:
    chat, address = await _load_chat_with_address(db, chat_id)
    ensure_participant(user, chat, address)

    body = payload.body.strip()
    ensure_message_has_content(body=body, attachment_count=0)
    # TODO(moderation): авто-фильтр оскорблений и контактов.

    message = AddressChatMessage(chat_id=chat.id, author_user_id=user.id, body=body)
    db.add(message)
    chat.last_message_at = utcnow()
    await mark_read(db, chat_id=chat.id, user_id=user.id, when=utcnow())
    await db.commit()
    await db.refresh(message)

    provider_name = await _provider_name_for(db, address)
    return await _publish(
        db,
        chat=chat,
        address=address,
        message=message,
        author=user,
        attachments=[],
        provider_name=provider_name,
    )


@router.post("/{chat_id}/messages/upload", response_model=ChatMessageRead)
async def post_chat_message_with_files(
    chat_id: UUID,
    body: Annotated[str, Form(max_length=MAX_MESSAGE_LENGTH)] = "",
    files: list[UploadFile] = File(default_factory=list),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatMessageRead:
    """Сообщение с вложениями. Текст необязателен, если приложен файл."""
    chat, address = await _load_chat_with_address(db, chat_id)
    ensure_participant(user, chat, address)

    text = (body or "").strip()
    ensure_message_has_content(body=text, attachment_count=len(files))

    # Сначала читаем и проверяем всё, и только потом пишем. Иначе отказ на
    # третьем файле оставлял бы два первых в хранилище — откатить БД можно,
    # записанные объекты нет.
    payloads: list[tuple[str, bytes]] = []
    for upload in files:
        filename = upload.filename or "file"
        content = await upload.read()
        ensure_within_limits(content=content, original_filename=filename)
        content_type_for(filename)
        payloads.append((filename, content))

    message = AddressChatMessage(chat_id=chat.id, author_user_id=user.id, body=text)
    db.add(message)
    await db.flush()

    stored: list[ChatAttachmentRead] = []
    for filename, content in payloads:
        attachment, file_record = await attach_file(
            db=db,
            chat=chat,
            message=message,
            content=content,
            original_filename=filename,
            user=user,
        )
        stored.append(
            ChatAttachmentRead(
                id=attachment.id,
                original_filename=file_record.original_filename,
                content_type=file_record.content_type,
                size_bytes=file_record.size_bytes,
                download_url=attachment_download_url(chat.id, attachment.id),
            )
        )

    chat.last_message_at = utcnow()
    await mark_read(db, chat_id=chat.id, user_id=user.id, when=utcnow())
    await db.commit()
    await db.refresh(message)

    provider_name = await _provider_name_for(db, address)
    return await _publish(
        db,
        chat=chat,
        address=address,
        message=message,
        author=user,
        attachments=stored,
        provider_name=provider_name,
    )


@router.get("/{chat_id}/attachments/{attachment_id}/download", response_model=None)
async def download_chat_attachment(
    chat_id: UUID,
    attachment_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    chat, address = await _load_chat_with_address(db, chat_id)
    ensure_participant(user, chat, address)
    file_record = await load_attachment(db=db, chat_id=chat.id, attachment_id=attachment_id)

    # nosniff — чтобы браузер не пытался «угадать» тип и отрисовать вложение
    # как страницу с нашего же домена.
    headers = {"X-Content-Type-Options": "nosniff"}
    try:
        local_path = local_stored_file_path(file_record)
        if local_path is not None:
            return FileResponse(
                local_path,
                filename=file_record.original_filename,
                media_type=file_record.content_type,
                headers=headers,
            )
        return Response(
            content=await read_stored_file_async(file_record),
            media_type=file_record.content_type,
            headers={
                **headers,
                "Content-Disposition": (
                    f'attachment; filename="{file_record.original_filename}"'
                ),
            },
        )
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(e)) from e


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
) -> None:
    # Аутентификация WS — ТОЛЬКО через HttpOnly session-cookie. При same-origin
    # WS-handshake браузер сам прикладывает cookie.
    # Query-param ?token= намеренно не поддерживается: токен в URL утекает в
    # логи nginx/прокси, в history браузера и в Referer — это была дыра.
    from app.config import settings as _settings

    cookie_token = websocket.cookies.get(_settings.session_cookie_name)
    user = await _ws_resolve_user(cookie_token or "")
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
        if address is None or not is_participant(user, chat, address):
            await websocket.close(code=4403)
            return

    await websocket.accept()
    await hub.join(chat_id, user.id, websocket, staff=is_staff(user))
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
