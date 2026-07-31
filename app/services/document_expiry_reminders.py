"""Напоминания собственнику об истекающих документах по адресу.

Третий рассыльщик в системе, и он отличается от двух существующих каналом
доставки. Напоминания по договорам и по срокам этапов — это события заявки
(ApplicationEvent): у них всегда есть заявка, к которой их привязать. У
документа адреса заявки нет, поэтому здесь персональные уведомления
(UserNotification) конкретным пользователям организации-собственника.

Вехи те же, что у договоров: 30/7/1 день. Плюс однократное «просрочен» —
документ с истёкшим сроком не перестаёт быть проблемой на следующий день.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ADDRESS_DOCUMENT_LABELS, UserRole
from app.models.address import Address
from app.models.address_document import AddressDocument
from app.models.user import User
from app.models.user_notification import UserNotification

DEFAULT_MILESTONES_DAYS = (30, 7, 1, 0)

#: Вид уведомления — по нему же ищем уже отправленные.
NOTIFICATION_KIND = "address_document_expiring"


@dataclass(frozen=True)
class DocumentReminder:
    document_id: UUID
    user_id: UUID
    milestone_days: int


def _texts(document: AddressDocument, address: Address, days: int) -> tuple[str, str]:
    label = ADDRESS_DOCUMENT_LABELS.get(document.kind, "Документ")
    where = address.full_address
    if days == 0:
        return (
            f"{label} истекает сегодня",
            f"«{document.title}» по адресу {where} истекает сегодня. Загрузите новый документ.",
        )
    if days == 1:
        return (
            f"{label} истекает завтра",
            f"«{document.title}» по адресу {where} истекает завтра.",
        )
    return (
        f"{label} истекает через {days} дн.",
        f"«{document.title}» по адресу {where} действует до {document.expires_at.isoformat()}.",
    )


async def _already_sent(*, db: AsyncSession, document_id: UUID) -> set[int]:
    """Вехи, по которым уведомление об этом документе уже уходило.

    У персонального уведомления нет поля payload, как у события заявки, зато
    есть kind. Поэтому веха кодируется в него — `address_document_expiring:7`,
    — а документ находится по link_id.
    """
    result = await db.execute(
        select(UserNotification.kind).where(
            and_(
                UserNotification.link_type == "address_document",
                UserNotification.link_id == document_id,
            )
        )
    )
    sent: set[int] = set()
    for (kind,) in result.all():
        prefix = f"{NOTIFICATION_KIND}:"
        if isinstance(kind, str) and kind.startswith(prefix):
            try:
                sent.add(int(kind[len(prefix):]))
            except ValueError:
                continue
    return sent


async def send_document_expiry_reminders(
    *,
    db: AsyncSession,
    today: date,
    milestones_days: tuple[int, ...] = DEFAULT_MILESTONES_DAYS,
) -> list[DocumentReminder]:
    """Уведомляет собственников о документах, истекающих через milestones_days."""
    sent: list[DocumentReminder] = []

    for milestone in sorted(set(milestones_days), reverse=True):
        target = date.fromordinal(today.toordinal() + milestone)
        result = await db.execute(
            select(AddressDocument, Address)
            .join(Address, Address.id == AddressDocument.address_id)
            .where(AddressDocument.expires_at == target)
        )
        for document, address in result.all():
            if milestone in await _already_sent(db=db, document_id=document.id):
                continue

            users_result = await db.execute(
                select(User).where(
                    and_(
                        User.provider_id == address.provider_id,
                        User.role == UserRole.OWNER.value,
                        User.is_active.is_(True),
                    )
                )
            )
            title, body = _texts(document, address, milestone)
            for user in users_result.scalars().all():
                db.add(
                    UserNotification(
                        user_id=user.id,
                        # Веха закодирована в kind: у персонального уведомления
                        # нет payload, а без вехи повторный прогон в другой день
                        # считал бы уведомление уже отправленным.
                        kind=f"{NOTIFICATION_KIND}:{milestone}",
                        title=title,
                        body=body,
                        link_type="address_document",
                        link_id=document.id,
                    )
                )
                sent.append(
                    DocumentReminder(
                        document_id=document.id,
                        user_id=user.id,
                        milestone_days=milestone,
                    )
                )
    return sent
