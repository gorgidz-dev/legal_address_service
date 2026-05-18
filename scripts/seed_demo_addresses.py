"""Демо-сидер: добавляет адреса с фотографиями и доп.услугами.

Фотографии тянутся из интернета (Unsplash CDN — здания и офисы). Если сеть
недоступна или картинка не скачалась — фото генерируется Pillow-ом
(градиент + силуэт зданий + ярлык района) как запасной вариант.

Каждое фото проходит стандартный `process_image_bytes` и сохраняется в storage —
ровно как при реальной загрузке владельцем.

Для каждого адреса создаётся/находится запись справочника `fns_offices`
(каскад Регион→Город→ИФНС в каталоге).

Идемпотентен: пропускает адрес, если кадастровый номер уже существует.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import random
from dataclasses import dataclass
from decimal import Decimal

import httpx
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
from app.services.fns_office import get_or_create_fns_office
from app.services.storage import get_object_storage, safe_storage_filename


# Пул фотографий зданий и офисов (Unsplash CDN, стабильные id).
PHOTO_URLS: list[str] = [
    "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab",
    "https://images.unsplash.com/photo-1497366216548-37526070297c",
    "https://images.unsplash.com/photo-1497366811353-6870744d04b2",
    "https://images.unsplash.com/photo-1431540015161-0bf868a2d407",
    "https://images.unsplash.com/photo-1497366754035-f200968a6e72",
    "https://images.unsplash.com/photo-1460472178825-e5240623afd5",
    "https://images.unsplash.com/photo-1564069114553-7215e1ff1890",
    "https://images.unsplash.com/photo-1577760258779-e787a1733016",
    "https://images.unsplash.com/photo-1568992687947-868a62a9f521",
    "https://images.unsplash.com/photo-1524758631624-e2822e304c36",
    "https://images.unsplash.com/photo-1497215728101-856f4ea42174",
    "https://images.unsplash.com/photo-1542744173-8e7e53415bb0",
    "https://images.unsplash.com/photo-1556761175-5973dc0f32e7",
    "https://images.unsplash.com/photo-1604328698692-f76ea9498e76",
    "https://images.unsplash.com/photo-1486325212027-8081e485255e",
    "https://images.unsplash.com/photo-1494891848038-7bd202a2afeb",
    "https://images.unsplash.com/photo-1449157291145-7efd050a4d0e",
    "https://images.unsplash.com/photo-1502672260266-1c1ef2d93688",
    "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00",
    "https://images.unsplash.com/photo-1531973576160-7125cd663d86",
    "https://images.unsplash.com/photo-1416339306562-f3d12fefd36f",
    "https://images.unsplash.com/photo-1522071820081-009f0129c71c",
    "https://images.unsplash.com/photo-1497215842964-222b430dc094",
    "https://images.unsplash.com/photo-1577412647305-991150c7d163",
]
_PHOTO_PARAMS = "?auto=format&fit=crop&w=1280&h=960&q=70"


# (цвет верх, цвет низ) — для запасных Pillow-картинок.
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
    region: str
    city: str
    full_address: str
    cadastral_number: str
    fns_code: str           # федеральный код ИФНС (region+office), напр. "7847"
    fns_number: int         # локальный номер «ИФНС № N»
    fns_city: str           # форма для гарантийного письма, напр. "Санкт-Петербурге"
    price_6m: Decimal
    price_11m: Decimal
    correspondence_price: Decimal | None
    photo_count: int


def _d(value: str) -> Decimal:
    return Decimal(value)


SPECS: list[AddressSpec] = [
    AddressSpec("Центральный", "Санкт-Петербург", "Санкт-Петербург",
                "г. Санкт-Петербург, Невский пр-т, д. 88, лит. А, оф. 401",
                "78:31:0001523:2001", "7847", 25, "Санкт-Петербурге",
                _d("21000"), _d("36000"), _d("4000"), 3),
    AddressSpec("Адмиралтейский", "Санкт-Петербург", "Санкт-Петербург",
                "г. Санкт-Петербург, наб. реки Мойки, д. 73, помещ. 12",
                "78:32:0007710:2002", "7838", 7, "Санкт-Петербурге",
                _d("18000"), _d("30000"), None, 2),
    AddressSpec("Красногорск", "Московская область", "Красногорск",
                "Московская обл., г. Красногорск, ул. Ленина, д. 5, оф. 210",
                "50:11:0010204:2003", "5024", 22, "Красногорске",
                _d("14000"), _d("23000"), _d("3000"), 3),
    AddressSpec("Химки", "Московская область", "Химки",
                "Московская обл., г. Химки, Ленинградское ш., д. 16, оф. 33",
                "50:10:0020107:2004", "5047", 13, "Химках",
                _d("13000"), _d("21000"), _d("2800"), 2),
    AddressSpec("Центральный", "Новосибирская область", "Новосибирск",
                "г. Новосибирск, Красный пр-т, д. 35, оф. 508",
                "54:35:0101010:2005", "5406", 6, "Новосибирске",
                _d("12000"), _d("19000"), _d("2500"), 3),
    AddressSpec("Ленинский", "Свердловская область", "Екатеринбург",
                "г. Екатеринбург, ул. Малышева, д. 51, оф. 1904",
                "66:41:0030203:2006", "6671", 25, "Екатеринбурге",
                _d("13000"), _d("22000"), _d("3000"), 3),
    AddressSpec("Вахитовский", "Республика Татарстан", "Казань",
                "г. Казань, ул. Баумана, д. 44, оф. 7",
                "16:50:0011804:2007", "1655", 14, "Казани",
                _d("12000"), _d("20000"), _d("2600"), 2),
    AddressSpec("Нижегородский", "Нижегородская область", "Нижний Новгород",
                "г. Нижний Новгород, ул. Большая Покровская, д. 18, оф. 305",
                "52:18:0060115:2008", "5260", 20, "Нижнем Новгороде",
                _d("11000"), _d("18000"), None, 2),
    AddressSpec("Центральный", "Краснодарский край", "Краснодар",
                "г. Краснодар, ул. Красная, д. 145, оф. 612",
                "23:43:0208015:2009", "2310", 5, "Краснодаре",
                _d("12000"), _d("20000"), _d("2700"), 3),
    AddressSpec("Ленинский", "Самарская область", "Самара",
                "г. Самара, ул. Молодогвардейская, д. 204, оф. 41",
                "63:01:0708003:2010", "6315", 18, "Самаре",
                _d("10000"), _d("17000"), _d("2400"), 2),
    AddressSpec("Кировский", "Ростовская область", "Ростов-на-Дону",
                "г. Ростов-на-Дону, ул. Большая Садовая, д. 105, оф. 9",
                "61:44:0030505:2011", "6164", 24, "Ростове-на-Дону",
                _d("11000"), _d("18000"), _d("2500"), 3),
    AddressSpec("Центральный", "Воронежская область", "Воронеж",
                "г. Воронеж, пр-т Революции, д. 38, оф. 210",
                "36:34:0606021:2012", "3650", 12, "Воронеже",
                _d("10000"), _d("16000"), None, 2),
    AddressSpec("Центральный", "Челябинская область", "Челябинск",
                "г. Челябинск, пр-т Ленина, д. 21, оф. 506",
                "74:36:0042009:2013", "7451", 22, "Челябинске",
                _d("10000"), _d("16000"), _d("2300"), 2),
    AddressSpec("Кировский", "Республика Башкортостан", "Уфа",
                "г. Уфа, ул. Ленина, д. 70, оф. 318",
                "02:55:0102008:2014", "0276", 40, "Уфе",
                _d("10000"), _d("17000"), _d("2400"), 3),
    AddressSpec("Центральный", "Красноярский край", "Красноярск",
                "г. Красноярск, пр-т Мира, д. 91, оф. 404",
                "24:50:0300280:2015", "2466", 24, "Красноярске",
                _d("11000"), _d("18000"), None, 2),
    AddressSpec("Ленинский", "Пермский край", "Пермь",
                "г. Пермь, ул. Ленина, д. 58, оф. 27",
                "59:01:4410112:2016", "5904", 5, "Перми",
                _d("10000"), _d("16000"), _d("2300"), 3),
    AddressSpec("Центральный", "Волгоградская область", "Волгоград",
                "г. Волгоград, пр-т им. В.И. Ленина, д. 17, оф. 8",
                "34:34:0100012:2017", "3444", 9, "Волгограде",
                _d("9000"), _d("15000"), None, 2),
    AddressSpec("Центральный", "Тюменская область", "Тюмень",
                "г. Тюмень, ул. Республики, д. 142, оф. 611",
                "72:23:0428001:2018", "7202", 14, "Тюмени",
                _d("11000"), _d("18000"), _d("2500"), 3),
    AddressSpec("Центральный", "Калининградская область", "Калининград",
                "г. Калининград, Ленинский пр-т, д. 30, оф. 12",
                "39:15:0010101:2019", "3906", 9, "Калининграде",
                _d("12000"), _d("20000"), _d("2800"), 3),
    AddressSpec("Фрунзенский", "Приморский край", "Владивосток",
                "г. Владивосток, ул. Светланская, д. 83, оф. 215",
                "25:28:0100100:2020", "2536", 12, "Владивостоке",
                _d("13000"), _d("21000"), _d("3200"), 2),
]

SERVICES_CATALOG: list[tuple[str, Decimal]] = [
    (AddressServiceKind.GUARANTEE_LETTER.value, Decimal("1500")),
    (AddressServiceKind.LEASE_AGREEMENT.value, Decimal("3000")),
    (AddressServiceKind.OWNER_CONFIRMATION.value, Decimal("2000")),
    (AddressServiceKind.DOOR_SIGN.value, Decimal("2500")),
    (AddressServiceKind.MAIL_RECEPTION.value, Decimal("4500")),
    (AddressServiceKind.FNS_VISIT_PHOTO.value, Decimal("3500")),
    (AddressServiceKind.PHONE_ANSWERING.value, Decimal("6000")),
    (AddressServiceKind.VISITOR_RECEPTION.value, Decimal("5000")),
]


def _vertical_gradient(top, bottom, size):
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
    """Запасная «фотография» 1200×900: градиент + силуэт зданий + ярлык."""
    rng = random.Random(f"{spec.cadastral_number}-{variant_idx}")
    palette = PALETTE[(SPECS.index(spec) + variant_idx) % len(PALETTE)]
    img = _vertical_gradient(palette[0], palette[1], (1200, 900))
    draw = ImageDraw.Draw(img)

    base_y = 720
    for i in range(8):
        bw = rng.randint(90, 180)
        bh = rng.randint(120, 280)
        x = i * 150 - 30
        rect = [x, base_y - bh, x + bw, base_y]
        shade = (max(palette[0][0] - 40, 10), max(palette[0][1] - 40, 10),
                 max(palette[0][2] - 40, 10))
        draw.rectangle(rect, fill=shade)
        for ry in range(rect[1] + 10, rect[3] - 10, 26):
            for rx in range(rect[0] + 10, rect[2] - 10, 30):
                if rng.random() > 0.4:
                    draw.rectangle([rx, ry, rx + 16, ry + 16], fill=(255, 224, 138))
    draw.rectangle([0, base_y, 1200, 900], fill=(20, 22, 36))

    font_district = _load_font(78)
    font_meta = _load_font(28)
    font_caption = _load_font(32)

    label = f"{spec.city}".upper()
    tw = draw.textlength(label, font=font_district)
    draw.text(((1200 - tw) // 2, 240), label, fill=(255, 255, 255), font=font_district)
    sub = f"ИФНС № {spec.fns_number}  ·  {spec.region}  ·  фото {variant_idx + 1}"
    sw = draw.textlength(sub, font=font_meta)
    draw.text(((1200 - sw) // 2, 340), sub, fill=(230, 230, 255), font=font_meta)

    caption = spec.full_address.split(",", 1)[1].strip() if "," in spec.full_address else spec.full_address
    if len(caption) > 60:
        caption = caption[:57] + "…"
    cw = draw.textlength(caption, font=font_caption)
    draw.text(((1200 - cw) // 2, 400), caption, fill=(248, 250, 255), font=font_caption)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    return buf.getvalue()


async def _photo_bytes(
    client: httpx.AsyncClient, spec: AddressSpec, global_idx: int, variant_idx: int
) -> tuple[bytes, str]:
    """Скачивает фото из интернета; при сбое — генерирует Pillow-ом."""
    url = PHOTO_URLS[(global_idx * 3 + variant_idx) % len(PHOTO_URLS)] + _PHOTO_PARAMS
    try:
        resp = await client.get(url, follow_redirects=True, timeout=20.0)
        resp.raise_for_status()
        data = resp.content
        if data and resp.headers.get("content-type", "").startswith("image/"):
            return data, "интернет"
    except (httpx.HTTPError, OSError) as exc:
        print(f"       фото: сеть недоступна ({exc}) — генерирую локально")
    return _generate_photo_bytes(spec, variant_idx), "генерация"


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
        net_photos = 0
        async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 seed-bot"}) as client:
            for global_idx, spec in enumerate(SPECS):
                existing = (
                    await db.execute(
                        select(Address).where(Address.cadastral_number == spec.cadastral_number)
                    )
                ).scalar_one_or_none()
                if existing is not None:
                    print(f"[skip] {spec.city} / {spec.district}: уже есть")
                    continue

                office = await get_or_create_fns_office(
                    db,
                    code=spec.fns_code,
                    name=f"ИФНС России № {spec.fns_number} по {spec.fns_city}",
                    short_number=spec.fns_number,
                    region=spec.region,
                    city=spec.city,
                )

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
                    fns_city=spec.fns_city,
                    fns_office_id=office.id,
                    is_available=True,
                    publication_status=AddressPublicationStatus.PUBLISHED.value,
                )
                db.add(address)
                await db.flush()
                await db.refresh(address)
                created_addresses += 1

                for idx in range(spec.photo_count):
                    raw, source = await _photo_bytes(client, spec, global_idx, idx)
                    if source == "интернет":
                        net_photos += 1
                    processed = process_image_bytes(raw)
                    sha = hashlib.sha256(processed.content).hexdigest()
                    safe_name = safe_storage_filename(
                        f"{spec.city.lower()}-{idx + 1}.jpg"
                    )
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

                print(
                    f"[ok]   {spec.city} / {spec.district}: address + "
                    f"{spec.photo_count} фото + {len(SERVICES_CATALOG)} услуги"
                )

        await db.commit()
        print(
            f"Done: addresses={created_addresses}, photos={created_photos} "
            f"(из интернета {net_photos}), services={created_services}"
        )


if __name__ == "__main__":
    asyncio.run(_seed())
