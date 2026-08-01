"""Правила переписки: кто участник, кем подписано сообщение, что не прочитано.

Всё это лежит в одном месте намеренно. Проверка участия нужна пяти ручкам
(история, отправка, вложение, скачивание, websocket), и разъехавшиеся копии
такой проверки — это ровно тот случай, когда шестая ручка появляется без неё.
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import UserRole
from app.models.address import Address
from app.models.address_chat import AddressChat, AddressChatMessage, ChatRead
from app.models.application import Application
from app.models.user import User

#: Площадка в переписке. Это те же роли, что считаются сотрудниками в
#: документах заявки, — расхождение здесь означало бы, что юрист видит комплект
#: документов, но не может спросить о нём в чате.
STAFF_ROLES = frozenset({UserRole.ADMIN.value, UserRole.MANAGER.value, UserRole.LAWYER.value})

#: Как подписано сообщение площадки для клиента и собственника. Личное имя
#: оператора им не нужно, а сотрудники между собой видят автора по имени.
PLATFORM_SIGNATURE = "Площадка"


def is_staff(user: object) -> bool:
    return getattr(user, "role", None) in STAFF_ROLES


def author_side(user: object) -> str:
    """`client` | `owner` | `staff` — чьё это сообщение.

    Сторона, а не роль: клиенту важно отличить собственника от площадки, а
    manager от lawyer ему не различить и не нужно.
    """
    role = getattr(user, "role", None)
    if role == UserRole.OWNER.value:
        return "owner"
    if role in STAFF_ROLES:
        return "staff"
    return "client"


def display_name(author: User, *, viewer: object, provider_name: str) -> str:
    """Подпись автора глазами конкретного читателя."""
    side = author_side(author)
    if side == "staff":
        # Сотрудники видят, кто из коллег ответил; клиент и собственник — нет.
        if not is_staff(viewer):
            return PLATFORM_SIGNATURE
        return getattr(author, "full_name", "") or PLATFORM_SIGNATURE
    if side == "owner":
        return provider_name or getattr(author, "full_name", "") or "Собственник"
    return getattr(author, "full_name", "") or getattr(author, "email", "") or "Клиент"


def is_participant(user: object, chat: AddressChat, address: Address) -> bool:
    if getattr(user, "id", None) == chat.client_user_id:
        return True
    if getattr(user, "role", None) == UserRole.OWNER.value:
        # Явная проверка на None: без неё собственник, ещё не привязанный к
        # организации, совпал бы с адресом без провайдера — None == None.
        provider_id = getattr(user, "provider_id", None)
        return provider_id is not None and provider_id == address.provider_id
    return is_staff(user)


def ensure_participant(user: object, chat: AddressChat, address: Address) -> None:
    if not is_participant(user, chat, address):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к переписке")


async def participants_for_notice(
    db: AsyncSession, chat: AddressChat, address: Address
) -> list[User]:
    """Кому уходит уведомление о новом сообщении: клиент, собственники, площадка.

    Площадка получает уведомления наравне с остальными — иначе «переписка с
    администрацией» означала бы, что администрация молча читает, когда сама
    зайдёт. Если поток сообщений станет шумным, это фильтр по важности, а не
    возврат к молчаливому наблюдению.
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

    staff = (
        await db.execute(
            select(User).where(
                User.role.in_(sorted(STAFF_ROLES)),
                User.is_active.is_(True),
            )
        )
    ).scalars().all()

    seen = {user.id for user in out}
    out.extend(user for user in staff if user.id not in seen)
    return out


def ensure_application_access(user: object, application: Application) -> None:
    """Кто вправе видеть переписку по заявке — проверка ДО того, как ветка заведена.

    Порядок важен: если сначала завести ветку, а потом отказать, то на каждый
    чужой запрос в таблице появлялась бы строка. Правило то же, что у документов
    заявки (services/application_documents.py), только формулировки про переписку.
    """
    if is_staff(user):
        return
    role = getattr(user, "role", None)
    if role == UserRole.OWNER.value:
        provider_id = getattr(user, "provider_id", None)
        if provider_id is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Собственник не привязан к организации исполнителя",
            )
        if provider_id != application.provider_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Заявка назначена другому исполнителю"
            )
        return
    if role == UserRole.CLIENT.value and getattr(user, "id", None) == application.created_by:
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к переписке по этой заявке")


async def resolve_thread_for_application(
    db: AsyncSession, application: Application
) -> AddressChat:
    """Ветка переписки по заявке: та же пара (адрес, клиент), не новая.

    Заявок по одной паре бывает несколько — продление ссылается на первичку.
    Разговор при этом продолжается, поэтому ветку ищем по адресу и клиенту, а
    не заводим на каждую заявку свою.
    """
    if application.created_by is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Заявка заведена без клиентского аккаунта — переписки по ней нет",
        )
    author = await db.get(User, application.created_by)
    if author is None or author.role != UserRole.CLIENT.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Заявку завёл не клиент — переписки по ней нет",
        )

    chat = (
        await db.execute(
            select(AddressChat).where(
                AddressChat.address_id == application.address_id,
                AddressChat.client_user_id == application.created_by,
            )
        )
    ).scalar_one_or_none()
    if chat is None:
        chat = AddressChat(
            address_id=application.address_id,
            client_user_id=application.created_by,
        )
        db.add(chat)
        await db.flush()
    return chat


async def unread_counts(
    db: AsyncSession, *, chat_ids: list[UUID], user_id: UUID
) -> dict[UUID, int]:
    """Сколько чужих сообщений появилось после последнего прочтения.

    Своих сообщений в счётчике нет: отправитель их уже видел, и подсвечивать
    ему собственный ответ как непрочитанное — способ приучить не смотреть на
    счётчик вовсе.
    """
    if not chat_ids:
        return {}

    reads = dict(
        (
            await db.execute(
                select(ChatRead.chat_id, ChatRead.last_read_at).where(
                    ChatRead.user_id == user_id,
                    ChatRead.chat_id.in_(chat_ids),
                )
            )
        ).all()
    )

    rows = (
        await db.execute(
            select(
                AddressChatMessage.chat_id,
                AddressChatMessage.created_at,
            ).where(
                AddressChatMessage.chat_id.in_(chat_ids),
                AddressChatMessage.author_user_id != user_id,
            )
        )
    ).all()

    counts: dict[UUID, int] = {}
    for chat_id, created_at in rows:
        last_read = reads.get(chat_id)
        if last_read is None or created_at > last_read:
            counts[chat_id] = counts.get(chat_id, 0) + 1
    return counts


async def mark_read(
    db: AsyncSession, *, chat_id: UUID, user_id: UUID, when: datetime
) -> None:
    """Отметить ветку прочитанной до момента `when`.

    Метка только вперёд: параллельная вкладка, открытая на старой истории, не
    должна откатывать её назад и воскрешать уже прочитанное.
    """
    row = (
        await db.execute(
            select(ChatRead).where(
                ChatRead.chat_id == chat_id, ChatRead.user_id == user_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        db.add(ChatRead(chat_id=chat_id, user_id=user_id, last_read_at=when))
        return
    if when > row.last_read_at:
        row.last_read_at = when
