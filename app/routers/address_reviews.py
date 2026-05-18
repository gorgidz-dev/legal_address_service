"""Отзывы об адресах: создание клиентом, публичная лента, модерация админом.

Поток:
- Клиент с ЗАВЕРШЁННОЙ заявкой по адресу создаёт отзыв (rating 1-5 + текст).
  Отзыв стартует в статусе pending.
- Админ модерирует: publish (виден публично, влияет на средний рейтинг) или
  reject (скрыт).
- Собственник адреса может один раз публично ответить на опубликованный отзыв.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
    OwnerReplyCreate,
    PublicReviewRead,
    ReviewModerationAction,
)

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

    review.status = (
        ReviewStatus.PUBLISHED.value
        if payload.action == "publish"
        else ReviewStatus.REJECTED.value
    )
    review.moderated_by = admin.id
    review.moderated_at = utcnow()
    review.moderation_note = payload.note
    await db.commit()
    await db.refresh(review)

    address = await db.get(Address, review.address_id)
    author = await db.get(User, review.client_user_id)
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
