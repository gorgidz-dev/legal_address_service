from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPKMixin

if TYPE_CHECKING:
    from app.models.address import Address


class AddressService(UUIDPKMixin, TimestampMixin, Base):
    """Опциональная услуга на адресе с собственной ценой.

    Каталог `kind` фиксированный (enum AddressServiceKind), но какие из них
    предлагает конкретный собственник и за какую цену — настраивается тут.
    """

    __tablename__ = "address_services"
    __table_args__ = (
        UniqueConstraint("address_id", "kind", name="uq_address_services_kind"),
        CheckConstraint("price >= 0", name="address_services_price_non_negative"),
        CheckConstraint(
            "kind IN ("
            "'guarantee_letter', 'lease_agreement', 'owner_confirmation',"
            " 'door_sign', 'mail_reception', 'fns_visit_photo',"
            " 'phone_answering', 'visitor_reception'"
            ")",
            name="address_services_kind_valid",
        ),
    )

    address_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("addresses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)

    address: Mapped["Address"] = relationship(back_populates="services")
