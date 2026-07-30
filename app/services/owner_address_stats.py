"""Отдача по адресам собственника: заявки, сделки, выручка.

Считается по оплаченным платежам, а не по цене адреса из карточки: цена — это
прайс, а выручка — то, что действительно поступило. Заявка без оплаты в выручку
не идёт, сколько бы адрес ни стоил.

Оплаченным считается платёж в статусе `succeeded` — тот же признак, по которому
заявка переходит дальше по рабочему процессу (см. routers/payments).
"""
from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Numeric, case, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums import PaymentStatus
from app.models.application import Application
from app.models.payment import Payment
from app.schemas.owner_stats import OwnerAddressStats

#: Копеек в рубле. Платежи хранятся в копейках целым числом, чтобы не ловить
#: ошибку округления на сложении.
KOPEKS_IN_RUBLE = Decimal("100")


async def address_stats_for_owner(
    *,
    db: AsyncSession,
    provider_id: UUID,
) -> dict[UUID, OwnerAddressStats]:
    """Статистика по каждому адресу собственника, ключ — id адреса.

    Возвращает словарь, а не список: вызывающий подмешивает эти числа к уже
    загруженным адресам, и искать по списку ему пришлось бы вручную.
    """
    paid = Payment.status == PaymentStatus.SUCCEEDED.value

    stmt = (
        select(
            Application.address_id,
            # distinct — иначе заявка с двумя платежами посчиталась бы дважды.
            func.count(func.distinct(Application.id)).label("applications_total"),
            func.count(case((paid, Payment.id))).label("deals_paid"),
            func.coalesce(
                func.sum(case((paid, cast(Payment.amount_kopeks, Numeric)))),
                0,
            ).label("revenue_kopeks"),
            func.max(case((paid, Payment.paid_at))).label("last_paid_at"),
        )
        .select_from(Application)
        .outerjoin(Payment, Payment.application_id == Application.id)
        .where(Application.provider_id == provider_id)
        .group_by(Application.address_id)
    )

    result = await db.execute(stmt)
    stats: dict[UUID, OwnerAddressStats] = {}
    for address_id, total, deals, revenue_kopeks, last_paid_at in result.all():
        stats[address_id] = OwnerAddressStats(
            address_id=address_id,
            applications_total=total or 0,
            deals_paid=deals or 0,
            revenue=Decimal(revenue_kopeks or 0) / KOPEKS_IN_RUBLE,
            last_paid_at=last_paid_at,
        )
    return stats
