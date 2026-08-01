"""Внутренняя оценка работы собственника.

ВАЖНО: это НЕ рейтинг адреса. Оценку адреса ставят клиенты (address_reviews),
она публичная и попадает в карточку. Здесь — оценка того, как собственник
работает с площадкой, и она внутренняя: решение владельца от 30.07.2026,
«клиенту об этом знать не нужно». Наружу не отдаётся ни в каком виде.

Три метрики, каждая из уже существующих данных:

  ответ         — медиана времени до первого ответа собственника в чате;
  карточки      — доля заполненности карточек адресов;
  документы     — доля возвратов комплекта на доработку.

Медиана, а не среднее: один отпуск на две недели утащил бы среднее так, что
им нельзя было бы пользоваться.

Метрика без данных не считается нулём. Собственник без единого чата не
«отвечает плохо» — про него просто ничего не известно, и в итоговый балл
такая метрика не входит вовсе. Иначе новый собственник получал бы двойку за
то, что ему ещё не писали.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import ApplicationEventKind, ApplicationStatus
from app.models.address import Address
from app.models.address_chat import AddressChat, AddressChatMessage
from app.models.application import Application
from app.models.application_event import ApplicationEvent

#: Ответ за это время и быстрее — полный балл; вдвое дольше — ноль.
GOOD_RESPONSE_HOURS = 4.0
BAD_RESPONSE_HOURS = 48.0

#: Что считается заполненной карточкой. Вес у всех одинаковый: спорить о
#: важности фото против описания можно долго, а пользы от этого нет.
CARD_FIELDS = ("description", "amenities", "price", "fns")

#: Целевые статусы, означающие возврат комплекта собственнику. Добавят в
#: рабочий процесс ещё один возврат — дописывать сюда.
RETURN_STATUSES = (ApplicationStatus.DOCUMENTS_REVISION.value,)


@dataclass(frozen=True)
class Metric:
    """Значение метрики. `value` в её собственных единицах, `score` — 0..1."""

    value: float | None
    score: float | None
    #: На скольких наблюдениях посчитано. 0 — метрика не участвует в итоге.
    sample: int


@dataclass(frozen=True)
class ProviderRating:
    provider_id: UUID
    response: Metric
    cards: Metric
    documents: Metric
    #: Итог 0..100 или None, если ни по одной метрике нет данных.
    score: int | None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def response_score(hours: float) -> float:
    """Линейно от полного балла за 4 часа до нуля за двое суток."""
    if hours <= GOOD_RESPONSE_HOURS:
        return 1.0
    if hours >= BAD_RESPONSE_HOURS:
        return 0.0
    span = BAD_RESPONSE_HOURS - GOOD_RESPONSE_HOURS
    return _clamp(1.0 - (hours - GOOD_RESPONSE_HOURS) / span)


def card_completeness(address: Address) -> float:
    """Доля заполненных полей карточки — 0..1."""
    filled = 0
    if (getattr(address, "description", None) or "").strip():
        filled += 1
    if getattr(address, "amenities", None):
        filled += 1
    if getattr(address, "price_11m", None):
        filled += 1
    if getattr(address, "fns_number", None):
        filled += 1
    return filled / len(CARD_FIELDS)


def _first_response_hours(messages: list[AddressChatMessage], owner_user_ids: set[UUID]) -> list[float]:
    """Часы до первого ответа собственника после каждого сообщения клиента.

    Считается только первая реплика собственника подряд: если клиент написал
    три сообщения, а собственник ответил один раз, это одно ожидание, а не три.
    """
    waits: list[float] = []
    pending: datetime | None = None
    for message in sorted(messages, key=lambda m: m.created_at):
        is_owner = message.author_user_id in owner_user_ids
        if not is_owner:
            if pending is None:
                pending = message.created_at
            continue
        if pending is not None:
            waits.append((message.created_at - pending).total_seconds() / 3600)
            pending = None
    return waits


def build_rating(
    *,
    provider_id: UUID,
    response_waits: list[float],
    addresses: list[Address],
    documents_total: int,
    documents_returned: int,
) -> ProviderRating:
    if response_waits:
        median = statistics.median(response_waits)
        response = Metric(value=median, score=response_score(median), sample=len(response_waits))
    else:
        response = Metric(value=None, score=None, sample=0)

    if addresses:
        completeness = sum(card_completeness(a) for a in addresses) / len(addresses)
        cards = Metric(value=completeness, score=_clamp(completeness), sample=len(addresses))
    else:
        cards = Metric(value=None, score=None, sample=0)

    if documents_total:
        return_rate = documents_returned / documents_total
        documents = Metric(
            value=return_rate, score=_clamp(1.0 - return_rate), sample=documents_total
        )
    else:
        documents = Metric(value=None, score=None, sample=0)

    scores = [m.score for m in (response, cards, documents) if m.score is not None]
    total = round(sum(scores) / len(scores) * 100) if scores else None
    return ProviderRating(
        provider_id=provider_id,
        response=response,
        cards=cards,
        documents=documents,
        score=total,
    )


async def ratings_for_all_providers(*, db: AsyncSession) -> dict[UUID, ProviderRating]:
    """Оценки по всем собственникам, ключ — provider_id."""
    addresses_result = await db.execute(select(Address))
    addresses_by_provider: dict[UUID, list[Address]] = {}
    address_to_provider: dict[UUID, UUID] = {}
    for address in addresses_result.scalars().all():
        addresses_by_provider.setdefault(address.provider_id, []).append(address)
        address_to_provider[address.id] = address.provider_id

    # Чаты: сообщения складываем по чату, автора-собственника вычисляем от
    # обратного — в чате по адресу все, кроме клиента, это сторона собственника.
    chats_result = await db.execute(select(AddressChat))
    chats = {chat.id: chat for chat in chats_result.scalars().all()}
    messages_result = await db.execute(select(AddressChatMessage))
    messages_by_chat: dict[UUID, list[AddressChatMessage]] = {}
    for message in messages_result.scalars().all():
        messages_by_chat.setdefault(message.chat_id, []).append(message)

    waits_by_provider: dict[UUID, list[float]] = {}
    for chat_id, messages in messages_by_chat.items():
        chat = chats.get(chat_id)
        if chat is None:
            continue
        provider_id = address_to_provider.get(chat.address_id)
        if provider_id is None:
            continue
        owner_ids = {
            m.author_user_id for m in messages if m.author_user_id != chat.client_user_id
        }
        waits_by_provider.setdefault(provider_id, []).extend(
            _first_response_hours(messages, owner_ids)
        )

    # Документы: сколько комплектов ушло на проверку и сколько вернулось.
    #
    # Возврат нельзя брать по одному лишь kind: correction_requested — это и
    # «переделай документы» собственнику, и «уточни данные» клиенту. Второе к
    # работе собственника отношения не имеет, и записав его в возвраты, мы
    # снижали бы ему оценку за чужие ошибки. Различаем по целевому статусу в
    # payload.
    events_result = await db.execute(
        select(
            ApplicationEvent.application_id,
            ApplicationEvent.kind,
            ApplicationEvent.payload,
        ).where(
            ApplicationEvent.kind.in_(
                (
                    ApplicationEventKind.DOCUMENT_UPLOADED.value,
                    ApplicationEventKind.CORRECTION_REQUESTED.value,
                )
            )
        )
    )
    apps_result = await db.execute(select(Application.id, Application.provider_id))
    provider_of_application = {row[0]: row[1] for row in apps_result.all()}

    totals: dict[UUID, int] = {}
    returns: dict[UUID, int] = {}
    for application_id, kind, payload in events_result.all():
        provider_id = provider_of_application.get(application_id)
        if provider_id is None:
            continue
        if kind == ApplicationEventKind.DOCUMENT_UPLOADED.value:
            totals[provider_id] = totals.get(provider_id, 0) + 1
        elif (payload or {}).get("status") in RETURN_STATUSES:
            returns[provider_id] = returns.get(provider_id, 0) + 1

    provider_ids = (
        set(addresses_by_provider)
        | set(waits_by_provider)
        | set(totals)
        | set(returns)
    )
    return {
        provider_id: build_rating(
            provider_id=provider_id,
            response_waits=waits_by_provider.get(provider_id, []),
            addresses=addresses_by_provider.get(provider_id, []),
            documents_total=totals.get(provider_id, 0),
            documents_returned=returns.get(provider_id, 0),
        )
        for provider_id in provider_ids
    }

