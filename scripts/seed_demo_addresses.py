"""Демо-сидер: добавляет несколько адресов с фотографиями и доп.услугами.

Фотографии генерируются Pillow-ом (градиент + большой ярлык района + ИФНС-чип),
пропускаются через стандартный `process_image_bytes` и сохраняются в storage —
ровно как при реальной загрузке владельцем.

Идемпотентен: пропускает адрес, если кадастровый номер уже существует.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import random
from dataclasses import dataclass
from decimal import Decimal
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.enums import (
    AddressPhotoModerationStatus,
    AddressPublicationStatus,
    AddressServiceKind,
    UserRole,
)
from app.models.address import Address
from app.models.address_photo import AddressPhoto
from app.models.address_service import AddressService
from app.models.provider import Provider
from app.models.user import User
from app.services.address_photos import (
    OUTPUT_CONTENT_TYPE,
    OUTPUT_EXTENSION,
    process_image_bytes,
)
from app.services.storage import get_object_storage, safe_storage_filename


# (название района-ярлыка, цвет фоновой плашки) -> для разнообразия картинок
PALETTE: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = [
    ((61, 70, 199), (148, 165, 240)),     # indigo
    ((11, 102, 102), (115, 196, 196)),    # teal
    ((176, 86, 32), (240, 188, 138)),     # amber
    ((146, 38, 90), (235, 156, 196)),     # rose
    ((52, 122, 60), (172, 220, 178)),     # emerald
    ((58, 65, 92), (164, 174, 207)),      # slate
]


@dataclass(frozen=True)
class AddressSpec:
    district: str
    full_address: str
    cadastral_number: str
    fns_number: int
    price_6m: Decimal
    price_11m: Decimal
    correspondence_price: Decimal | None
    photo_count: int


SPECS: list[AddressSpec] = [
    AddressSpec(
        district="Хамовники",
        full_address="г. Москва, ул. Льва Толстого, д. 16, БЦ Юпитер, оф. 312",
        cadastral_number="77:01:0000000:1001",
        fns_number=4,
        price_6m=Decimal("28000.00"),
        price_11m=Decimal("46000.00"),
        correspondence_price=Decimal("5000.00"),
        photo_count=3,
    ),
    AddressSpec(
        district="Замоскворечье",
        full_address="г. Москва, Пятницкая ул., д. 24, стр. 2, оф. 17",
        cadastral_number="77:01:0000000:1002",
        fns_number=5,
        price_6m=Decimal("19000.00"),
        price_11m=Decimal("32000.00"),
        correspondence_price=Decimal("3500.00"),
        photo_count=2,
    ),
    AddressSpec(
        district="Басманный",
        full_address="г. Москва, Мясницкая ул., д. 13, стр. 18, помещ. 4",
        cadastral_number="77:01:0000000:1003",
        fns_number=9,
        price_6m=Decimal("17000.00"),
        price_11m=Decimal("28000.00"),
        correspondence_price=None,
        photo_count=2,
    ),
    AddressSpec(
        district="Тверской",
        full_address="г. Москва, ул. Малая Дмитровка, д. 9, стр. 3, оф. 7",
        cadastral_number="77:01:0000000:1004",
        fns_number=10,
        price_6m=Decimal("32000.00"),
        price_11m=Decimal("54000.00"),
        correspondence_price=Decimal("6000.00"),
        photo_count=3,
    ),
    AddressSpec(
        district="Арбат",
        full_address="г. Москва, Сивцев Вражек пер., д. 23, помещ. 2",
        cadastral_number="77:01:0000000:1005",
        fns_number=4,
        price_6m=Decimal("24000.00"),
        price_11m=Decimal("41000.00"),
        correspondence_price=Decimal("4500.00"),
        photo_count=2,
    ),
    AddressSpec(
        district="Пресненский",
        full_address="г. Москва, 1-й Тверской-Ямской пер., д. 28, стр. 1, оф. 18",
        cadastral_number="77:01:0000000:1006",
        fns_number=10,
        price_6m=Decimal("26000.00"),
        price_11m=Decimal("44000.00"),
        correspondence_price=Decimal("5000.00"),
        photo_count=3,
    ),
]

SERVICES_CATALOG: list[tuple[str, Decimal]] = [
    # Юр. документы
    (AddressServiceKind.GUARANTEE_LETTER.value, Decimal("1500")),
    (AddressServiceKind.LEASE_AGREEMENT.value, Decimal("3000")),
    (AddressServiceKind.OWNER_CONFIRMATION.value, Decimal("2000")),
    # Платный сервис на адресе
    (AddressServiceKind.DOOR_SIGN.value, Decimal("2500")),
    (AddressServiceKind.MAIL_RECEPTION.value, Decimal("4500")),
    (AddressServiceKind.FNS_VISIT_PHOTO.value, Decimal("3500")),
    (AddressServiceKind.PHONE_ANSWERING.value, Decimal("6000")),
    (AddressServiceKind.VISITOR_RECEPTION.value, Decimal("5000")),
]


def _vertical_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int], size: tuple[int, int]) -> Image.Image:
    w, h = size
    base = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(base)
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))
    return base


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _generate_photo_bytes(spec: AddressSpec, variant_idx: int) -> bytes:
    """Создаёт «фотографию» 1200×900: градиент + силуэт здания + ярлык района."""
    rng = random.Random(f"{spec.cadastral_number}-{variant_idx}")
    palette = PALETTE[(SPECS.index(spec) + variant_idx) % len(PALETTE)]
    img = _vertical_gradient(palette[0], palette[1], (1200, 900))
    draw = ImageDraw.Draw(img)

    # Силуэт «зданий» внизу
    base_y = 720
    for i in range(8):
        bw = rng.randint(90, 180)
        bh = rng.randint(120, 280)
        x = i * 150 - 30
        rect = [x, base_y - bh, x + bw, base_y]
        shade = max(palette[0][0] - 40, 10), max(palette[0][1] - 40, 10), max(palette[0][2] - 40, 10)
        draw.rectangle(rect, fill=shade)
        # окна
        for ry in range(rect[1] + 10, rect[3] - 10, 26):
            for rx in range(rect[0] + 10, rect[2] - 10, 30):
                lit = rng.random() > 0.4
                if lit:
                    draw.rectangle([rx, ry, rx + 16, ry + 16], fill=(255, 224, 138))
    # горизонт
    draw.rectangle([0, base_y, 1200, 900], fill=(20, 22, 36))

    # ярлык района сверху
    font_district = _load_font(86)
    font_meta = _load_font(28)
    font_caption = _load_font(34)

    label = spec.district.upper()
    tw = draw.textlength(label, font=font_district)
    draw.text(((1200 - tw) // 2, 240), label, fill=(255, 255, 255), font=font_district)
    sub = f"ИФНС № {spec.fns_number}  ·  фото {variant_idx + 1}"
    sw = draw.textlength(sub, font=font_meta)
    draw.text(((1200 - sw) // 2, 350), sub, fill=(230, 230, 255), font=font_meta)

    caption = spec.full_address.split(",", 1)[1].strip() if "," in spec.full_address else spec.full_address
    if len(caption) > 60:
        caption = caption[:57] + "…"
    cw = draw.textlength(caption, font=font_caption)
    draw.text(((1200 - cw) // 2, 410), caption, fill=(248, 250, 255), font=font_caption)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


async def _seed():
    storage = get_object_storage()
    async with AsyncSessionLocal() as db:
        provider = (
            await db.execute(
                select(Provider).where(Provider.short_name == "Московский адресный фонд")
            )
        ).scalar_one_or_none()
        if provider is None:
            print("Не нашёл провайдера 'Московский адресный фонд' — отмена")
            return

        admin = (
            await db.execute(
                select(User).where(User.role == UserRole.ADMIN.value).limit(1)
            )
        ).scalar_one_or_none()
        if admin is None:
            print("Нет пользователя с ролью admin — отмена")
            return

        created_addresses = 0
        created_photos = 0
        created_services = 0
        for spec in SPECS:
            # idempotency: skip if cadastral_number already exists
            existing = (
                await db.execute(
                    select(Address).where(Address.cadastral_number == spec.cadastral_number)
                )
            ).scalar_one_or_none()
            if existing is not None:
                print(f"[skip] {spec.district}: уже есть")
                continue

            address = Address(
                provider_id=provider.id,
                full_address=spec.full_address,
                room_number=None,
                cadastral_number=spec.cadastral_number,
                ownership_doc="Свидетельство о праве собственности",
                ownership_doc_short="Св-во о собств.",
                ownership_doc_pages=1,
                price_6m=spec.price_6m,
                price_11m=spec.price_11m,
                correspondence_price=spec.correspondence_price,
                fns_number=spec.fns_number,
                fns_city="Москве",
                is_available=True,
                publication_status=AddressPublicationStatus.PUBLISHED.value,
            )
            db.add(address)
            await db.flush()
            await db.refresh(address)
            created_addresses += 1

            # photos
            for idx in range(spec.photo_count):
                raw = _generate_photo_bytes(spec, idx)
                processed = process_image_bytes(raw)
                sha = hashlib.sha256(processed.content).hexdigest()
                safe_name = safe_storage_filename(f"{spec.district.lower()}-{idx + 1}.jpg")
                if not safe_name.lower().endswith(OUTPUT_EXTENSION):
                    safe_name = f"{safe_name}{OUTPUT_EXTENSION}"
                key = f"addresses/{address.id}/photos/{sha[:16]}/{safe_name}"
                stored = storage.put_bytes(
                    key=key,
                    content=processed.content,
                    content_type=OUTPUT_CONTENT_TYPE,
                )
                photo = AddressPhoto(
                    address_id=address.id,
                    storage_backend=stored.backend,
                    storage_key=stored.key,
                    original_filename=safe_name,
                    content_type=OUTPUT_CONTENT_TYPE,
                    size_bytes=len(processed.content),
                    width=processed.width,
                    height=processed.height,
                    sha256=sha,
                    moderation_status=AddressPhotoModerationStatus.APPROVED.value,
                    is_main=(idx == 0),
                    sort_order=idx,
                    uploaded_by=admin.id,
                )
                db.add(photo)
                created_photos += 1

            # services
            for kind, price in SERVICES_CATALOG:
                db.add(
                    AddressService(
                        address_id=address.id,
                        kind=kind,
                        price=price,
                        is_active=True,
                    )
                )
                created_services += 1

            print(f"[ok]   {spec.district}: address + {spec.photo_count} фото + {len(SERVICES_CATALOG)} услуги")

        await db.commit()
        print(
            f"Done: addresses={created_addresses}, photos={created_photos}, services={created_services}"
        )


if __name__ == "__main__":
    asyncio.run(_seed())
