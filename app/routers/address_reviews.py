"""Отзывы об адресах: создание клиентом, публичная лента, модерация админом.

Поток:
- Клиент с ЗАВЕРШЁННОЙ заявкой по адресу создаёт отзыв (rating 1-5 + текст).
  Отзыв стартует в статусе pending.
- Админ модерирует: publish (виден публично, влияет на средний рейтинг) или
  reject (скрыт).
- Собственник адреса может один раз публично ответить на опубликованный отзыв.
"""
from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_admin, utcnow
from app.database import get_db
from app.enums import ApplicationStatus, ReviewStatus, UserRole
from app.models.address import Address
from app.models.address_review import AddressReview
from app.models.application import Application
from app.models.user import User
from app.schemas.marketplace import (
    AddressReviewCreate,
    ModerationReviewRead,
    MyReviewRead,
    OwnerReplyCreate,
    PublicReviewRead,
    ReviewModerationAction,
)
from app.services.email_outbox import send_email
from app.services.notification_events import write_user_notification

logger = logging.getLogger("address_reviews")

router = APIRouter(prefix="/marketplace", tags=["address-reviews"])


def _mask_author_name(full_name: str) -> str:
    """Имя автора для витрины: «Алексей Морозов» → «Алексей М.».

    Не раскрываем полную фамилию — отзыв публичный.
    """
    parts = (full_name or "").strip().split()
    if not parts:
        return "Клиент"
    if len(parts) == 1:
        return parts[0]
    return f"{parts[0]} {parts[1][0]}."


def _public_review(review: AddressReview, author_full_name: str) -> PublicReviewRead:
    return PublicReviewRead(
        id=review.id,
        rating=review.rating,
        body=review.body,
        author_name=_mask_author_name(author_full_name),
        created_at=review.created_at,
        owner_reply=review.owner_reply,
        owner_reply_at=review.owner_reply_at,
    )


# ============================== Client: create ==============================


@router.post(
    "/addresses/{address_id}/reviews",
    response_model=PublicReviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_review(
    address_id: UUID,
    payload: AddressReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PublicReviewRead:
    if user.role != UserRole.CLIENT.value:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Отзыв может оставить только клиент"
        )

    address = await db.get(Address, address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")

    # Verified purchase: нужна завершённая заявка клиента по этому адресу.
    completed_application = (
        await db.execute(
            select(Application).where(
                Application.address_id == address_id,
                Application.created_by == user.id,
                Application.status == ApplicationStatus.COMPLETED.value,
            )
        )
    ).scalars().first()
    if completed_application is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Отзыв можно оставить только по завершённой заявке на этот адрес",
        )

    # Один отзыв на пару (адрес, клиент).
    existing = (
        await db.execute(
            select(AddressReview).where(
                AddressReview.address_id == address_id,
                AddressReview.client_user_id == user.id,
            )
        )
    ).scalars().first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Вы уже оставляли отзыв на этот адрес"
        )

    review = AddressReview(
        address_id=address_id,
        client_user_id=user.id,
        application_id=completed_application.id,
        rating=payload.rating,
        body=payload.body.strip(),
        status=ReviewStatus.PENDING.value,
    )
    db.add(review)
    await db.commit()
    await db.refresh(review)
    return _public_review(review, user.full_name)


# ============================== Public: list ==============================


@router.get(
    "/addresses/{address_id}/reviews", response_model=list[PublicReviewRead]
)
async def list_address_reviews(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[PublicReviewRead]:
    """Только опубликованные отзывы. Публичный эндпоинт."""
    rows = (
        await db.execute(
            select(AddressReview, User)
            .join(User, User.id == AddressReview.client_user_id)
            .where(
                AddressReview.address_id == address_id,
                AddressReview.status == ReviewStatus.PUBLISHED.value,
            )
            .order_by(AddressReview.created_at.desc())
        )
    ).all()
    return [_public_review(review, author.full_name) for review, author in rows]


def _my_review(review: AddressReview) -> MyReviewRead:
    return MyReviewRead(
        id=review.id,
        address_id=review.address_id,
        rating=review.rating,
        body=review.body,
        status=review.status,
        moderation_note=review.moderation_note,
        owner_reply=review.owner_reply,
        created_at=review.created_at,
    )


# ====================== Client: own review (edit / delete) ======================


@router.get(
    "/addresses/{address_id}/reviews/mine",
    response_model=Optional[MyReviewRead],
)
async def get_my_review(
    address_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Optional[MyReviewRead]:
    """Собственный отзыв клиента по адресу (любой статус) — или null."""
    review = (
        await db.execute(
            select(AddressReview).where(
                AddressReview.address_id == address_id,
                AddressReview.client_user_id == user.id,
            )
        )
    ).scalars().first()
    return _my_review(review) if review is not None else None


@router.patch("/reviews/{review_id}", response_model=MyReviewRead)
async def update_my_review(
    review_id: UUID,
    payload: AddressReviewCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MyReviewRead:
    """Редактирование своего отзыва. Возвращает его на повторную модерацию."""
    review = await db.get(AddressReview, review_id)
    if review is None or review.client_user_id != user.id:
        # Не подтверждаем существование чужого отзыва.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отзыв не найден")

    review.rating = payload.rating
    review.body = payload.body.strip()
    # Изменённый текст должен пройти модерацию заново — сбрасываем в pending.
    review.status = ReviewStatus.PENDING.value
    review.moderated_by = None
    review.moderated_at = None
    review.moderation_note = None
    await db.commit()
    await db.refresh(review)
    return _my_review(review)


@router.delete("/reviews/{review_id}")
async def delete_my_review(
    review_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    review = await db.get(AddressReview, review_id)
    if review is None or review.client_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отзыв не найден")
    await db.delete(review)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================== Owner: reply ==============================


@router.post(
    "/reviews/{review_id}/owner-reply", response_model=PublicReviewRead
)
async def owner_reply_to_review(
    review_id: UUID,
    payload: OwnerReplyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PublicReviewRead:
    review = await db.get(AddressReview, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отзыв не найден")
    # Отвечать можно только на опубликованный отзыв — pending/rejected скрыты.
    if review.status != ReviewStatus.PUBLISHED.value:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отзыв не найден")

    address = await db.get(Address, review.address_id)
    if address is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Адрес не найден")
    is_owner = (
        user.role == UserRole.OWNER.value
        and user.provider_id is not None
        and user.provider_id == address.provider_id
    )
    if not is_owner:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Ответить на отзыв может только собственник этого адреса",
        )
    if review.owner_reply is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Ответ на этот отзыв уже оставлен"
        )

    review.owner_reply = payload.body.strip()
    review.owner_reply_at = utcnow()
    await db.commit()
    await db.refresh(review)

    author = await db.get(User, review.client_user_id)
    return _public_review(review, author.full_name if author else "")


async def _notify_review_moderated(
    db: AsyncSession,
    *,
    review: AddressReview,
    address: Address | None,
    author: User | None,
    published: bool,
) -> None:
    """Уведомляет автора об итоге модерации отзыва: in-app запись + email.

    Сбой уведомления не должен ломать саму модерацию — всё под try/except.
    Ссылку в in-app не кладём: спец-route для отзыва нет, адрес назван в тексте.
    """
    if author is None:
        return
    address_short = (address.full_address[:80] if address else "адрес")
    if published:
        title = "Ваш отзыв опубликован"
        body = (
            f"Отзыв об адресе «{address_short}» прошёл модерацию и теперь "
            f"виден в каталоге. Спасибо!"
        )
    else:
        reason = f" Причина: {review.moderation_note}." if review.moderation_note else ""
        title = "Ваш отзыв отклонён"
        body = (
            f"Отзыв об адресе «{address_short}» не прошёл модерацию.{reason} "
            f"Вы можете отредактировать его в карточке адреса."
        )
    try:
        await write_user_notification(
            db,
            user_id=review.client_user_id,
            kind="review_moderated",
            title=title,
            body=body,
        )
        await db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("review-moderated notif failed review=%s", review.id, exc_info=True)
    try:
        await send_email(to=author.email, subject=title, body=body)
    except Exception:  # noqa: BLE001
        logger.warning("review-moderated email failed review=%s", review.id, exc_info=True)


# ============================== Admin: moderation ==============================

admin_router = APIRouter(
    prefix="/admin",
    tags=["address-reviews"],
    dependencies=[Depends(require_admin)],
)


@admin_router.get("/reviews", response_model=list[ModerationReviewRead])
async def admin_list_reviews(
    review_status: ReviewStatus = Query(default=ReviewStatus.PENDING, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> list[ModerationReviewRead]:
    rows = (
        await db.execute(
            select(AddressReview, Address, User)
            .join(Address, Address.id == AddressReview.address_id)
            .join(User, User.id == AddressReview.client_user_id)
            .where(AddressReview.status == review_status.value)
            .order_by(AddressReview.created_at.asc())
        )
    ).all()
    return [
        ModerationReviewRead(
            id=review.id,
            address_id=address.id,
            address_full=address.full_address,
            client_email=author.email,
            rating=review.rating,
            body=review.body,
            status=review.status,
            moderation_note=review.moderation_note,
            moderated_at=review.moderated_at,
            owner_reply=review.owner_reply,
            created_at=review.created_at,
        )
        for review, address, author in rows
    ]


@admin_router.post(
    "/reviews/{review_id}/moderate", response_model=ModerationReviewRead
)
async def moderate_review(
    review_id: UUID,
    payload: ReviewModerationAction,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_admin),
) -> ModerationReviewRead:
    review = await db.get(AddressReview, review_id)
    if review is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отзыв не найден")
    if review.status != ReviewStatus.PENDING.value:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Модерировать можно только pending-отзыв, текущий статус: {review.status}",
        )

    published = payload.action == "publish"
    review.status = (
        ReviewStatus.PUBLISHED.value if published else ReviewStatus.REJECTED.value
    )
    review.moderated_by = admin.id
    review.moderated_at = utcnow()
    review.moderation_note = payload.note
    await db.commit()
    await db.refresh(review)

    address = await db.get(Address, review.address_id)
    author = await db.get(User, review.client_user_id)

    # Уведомляем автора об итоге модерации — in-app + email.
    # Ошибки уведомления не должны ломать саму модерацию.
    await _notify_review_moderated(
        db, review=review, address=address, author=author, published=published
    )

    return ModerationReviewRead(
        id=review.id,
        address_id=review.address_id,
        address_full=address.full_address if address else "",
        client_email=author.email if author else "",
        rating=review.rating,
        body=review.body,
        status=review.status,
        moderation_note=review.moderation_note,
        moderated_at=review.moderated_at,
        owner_reply=review.owner_reply,
        created_at=review.created_at,
    )
