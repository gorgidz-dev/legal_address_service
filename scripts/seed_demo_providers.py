"""Витринный набор собственников и адресов для каталога.

Зачем: до подключения реальных собственников каталог пуст, и посетитель видит
пустой маркетплейс. Скрипт наполняет витрину 25 карточками, которые потом
замещаются реальными по одной.

Всё созданное помечено:
- `providers.code` начинается с `DEMO-`;
- `addresses.notes` содержит маркер `[DEMO]`.

Благодаря маркерам набор снимается одной командой:

    python -m scripts.seed_demo_providers --purge

Важно: у демо-собственников НЕТ пользовательских аккаунтов. Заявка на такой
адрес не сможет уйти дальше проверки администратором — принять её от имени
собственника некому. Это намеренно: деньги не могут молча уйти за адрес,
которого не существует.

Фотографии берутся из локального каталога (Pexels License — свободно для
коммерческого использования, без указания авторства), прогоняются через тот же
конвейер, что и загрузки собственников (нормализация в JPEG), и кладутся в
основное объектное хранилище.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import pathlib
import random
import sys
from decimal import Decimal

from sqlalchemy import delete, select

from app.database import AsyncSessionLocal
from app.enums import AddressPhotoModerationStatus, AddressPublicationStatus, UserRole
from app.models.address import Address
from app.models.address_photo import AddressPhoto
from app.models.address_service import AddressService
from app.models.provider import Provider
from app.models.user import User
from app.services.address_photos import process_image_bytes
from app.services.storage import get_object_storage

DEMO_CODE_PREFIX = "DEMO-"
DEMO_NOTE_MARKER = "[DEMO]"

# Координаты центров городов — чтобы карточки появились на карте. Точность до
# города достаточна: это витрина, а не реальные объекты.
CITY_COORDS: dict[str, tuple[float, float]] = {
    "Москва": (55.7558, 37.6173),
    "Санкт-Петербург": (59.9343, 30.3351),
    "Екатеринбург": (56.8389, 60.6057),
    "Новосибирск": (55.0084, 82.9357),
    "Казань": (55.7963, 49.1088),
    "Нижний Новгород": (56.3269, 44.0059),
    "Ростов-на-Дону": (47.2225, 39.7187),
    "Краснодар": (45.0355, 38.9753),
    "Самара": (53.1959, 50.1002),
    "Челябинск": (55.1644, 61.4368),
}

# (город, улица/дом, помещение, № ИФНС, город ИФНС в предложном падеже)
LISTINGS: list[tuple[str, str, str, int, str]] = [
    ("Москва", "ул. Академика Королёва, д. 13, стр. 1", "офис 214", 46, "Москве"),
    ("Москва", "Дмитровское шоссе, д. 71Б", "офис 305", 46, "Москве"),
    ("Москва", "ул. Нижняя Сыромятническая, д. 10, стр. 9", "офис 412", 46, "Москве"),
    ("Москва", "Варшавское шоссе, д. 125, стр. 1", "офис 118", 46, "Москве"),
    ("Москва", "ул. Профсоюзная, д. 84/32, корп. 1", "офис 27", 46, "Москве"),
    ("Санкт-Петербург", "Лиговский проспект, д. 140, лит. А", "офис 320", 15, "Санкт-Петербургу"),
    ("Санкт-Петербург", "ул. Оптиков, д. 4, корп. 2", "офис 511", 15, "Санкт-Петербургу"),
    ("Санкт-Петербург", "Свердловская набережная, д. 44, лит. Ю", "офис 208", 15, "Санкт-Петербургу"),
    ("Санкт-Петербург", "проспект Обуховской Обороны, д. 120, лит. Е", "офис 415", 15, "Санкт-Петербургу"),
    ("Екатеринбург", "ул. Малышева, д. 51", "офис 1704", 39, "Екатеринбургу"),
    ("Екатеринбург", "ул. Радищева, д. 28", "офис 602", 39, "Екатеринбургу"),
    ("Новосибирск", "Красный проспект, д. 86", "офис 407", 51, "Новосибирску"),
    ("Новосибирск", "ул. Кирова, д. 113", "офис 1201", 51, "Новосибирску"),
    ("Казань", "ул. Петербургская, д. 50, корп. 5", "офис 318", 18, "Казани"),
    ("Казань", "проспект Ямашева, д. 10", "офис 205", 18, "Казани"),
    ("Нижний Новгород", "ул. Родионова, д. 165, корп. 13", "офис 504", 52, "Нижнему Новгороду"),
    ("Нижний Новгород", "ул. Максима Горького, д. 117", "офис 812", 52, "Нижнему Новгороду"),
    ("Ростов-на-Дону", "проспект Михаила Нагибина, д. 14А", "офис 610", 60, "Ростову-на-Дону"),
    ("Ростов-на-Дону", "ул. Красноармейская, д. 200", "офис 303", 60, "Ростову-на-Дону"),
    ("Краснодар", "ул. Красная, д. 176", "офис 419", 23, "Краснодару"),
    ("Краснодар", "ул. Академика Пустовойта, д. 5", "офис 112", 23, "Краснодару"),
    ("Самара", "Московское шоссе, д. 4, корп. 15", "офис 707", 63, "Самаре"),
    ("Самара", "ул. Ново-Садовая, д. 106, корп. 109", "офис 226", 63, "Самаре"),
    ("Челябинск", "проспект Ленина, д. 21В", "офис 815", 74, "Челябинску"),
    ("Челябинск", "ул. Труда, д. 156", "офис 402", 74, "Челябинску"),
]

COMPANY_NAMES: list[tuple[str, str]] = [
    ("Астра Групп", "Общество с ограниченной ответственностью «Астра Групп»"),
    ("Бизнес-Парк Север", "Общество с ограниченной ответственностью «Бизнес-Парк Север»"),
    ("Вектор Недвижимость", "Общество с ограниченной ответственностью «Вектор Недвижимость»"),
    ("Гранд Офис", "Общество с ограниченной ответственностью «Гранд Офис»"),
    ("Дельта Эстейт", "Общество с ограниченной ответственностью «Дельта Эстейт»"),
    ("Инвест Плаза", "Общество с ограниченной ответственностью «Инвест Плаза»"),
    ("Капитал Строй", "Общество с ограниченной ответственностью «Капитал Строй»"),
    ("Лидер Реалти", "Общество с ограниченной ответственностью «Лидер Реалти»"),
    ("Меридиан Активы", "Общество с ограниченной ответственностью «Меридиан Активы»"),
    ("Невский Актив", "Общество с ограниченной ответственностью «Невский Актив»"),
    ("Олимп Девелопмент", "Общество с ограниченной ответственностью «Олимп Девелопмент»"),
    ("Партнёр Офис", "Общество с ограниченной ответственностью «Партнёр Офис»"),
    ("Респект Недвижимость", "Общество с ограниченной ответственностью «Респект Недвижимость»"),
    ("Сигма Ассетс", "Общество с ограниченной ответственностью «Сигма Ассетс»"),
    ("Титан Проперти", "Общество с ограниченной ответственностью «Титан Проперти»"),
    ("Уником Групп", "Общество с ограниченной ответственностью «Уником Групп»"),
    ("Форум Плаза", "Общество с ограниченной ответственностью «Форум Плаза»"),
    ("Хоризонт Офис", "Общество с ограниченной ответственностью «Хоризонт Офис»"),
    ("Центр Актив", "Общество с ограниченной ответственностью «Центр Актив»"),
    ("Эверест Реалти", "Общество с ограниченной ответственностью «Эверест Реалти»"),
    ("Южный Двор", "Общество с ограниченной ответственностью «Южный Двор»"),
    ("Янтарь Эстейт", "Общество с ограниченной ответственностью «Янтарь Эстейт»"),
    ("Атлант Офис", "Общество с ограниченной ответственностью «Атлант Офис»"),
    ("Балтика Проперти", "Общество с ограниченной ответственностью «Балтика Проперти»"),
    ("Волга Девелопмент", "Общество с ограниченной ответственностью «Волга Девелопмент»"),
]

SIGNATORIES: list[tuple[str, str, str]] = [
    ("Соколов Игорь Петрович", "Соколова Игоря Петровича", "И.П. Соколов"),
    ("Ковалёва Марина Сергеевна", "Ковалёвой Марины Сергеевны", "М.С. Ковалёва"),
    ("Лебедев Артём Николаевич", "Лебедева Артёма Николаевича", "А.Н. Лебедев"),
    ("Новикова Елена Викторовна", "Новиковой Елены Викторовны", "Е.В. Новикова"),
    ("Морозов Дмитрий Алексеевич", "Морозова Дмитрия Алексеевича", "Д.А. Морозов"),
]

DESCRIPTIONS: list[str] = [
    "Отдельное помещение в действующем бизнес-центре. Собственник на связи, "
    "готов встретить инспектора ФНС и подтвердить нахождение компании по адресу.",
    "Офис в здании с охраной и постоянным пропускным режимом. Почта принимается "
    "ежедневно, о поступлении корреспонденции сообщаем в тот же день.",
    "Помещение с отдельным входом и возможностью разместить табличку компании. "
    "Подходит и для первичной регистрации, и для смены адреса действующего ООО.",
    "Адрес не входит в перечень массовой регистрации. Собственник предоставляет "
    "полный комплект: гарантийное письмо, договор аренды, свежую выписку ЕГРН.",
    "Бизнес-центр рядом с метро, есть парковка для посетителей. По запросу "
    "организуем осмотр помещения и встречу с представителем собственника.",
]

# (вид услуги, минимальная цена, максимальная цена)
SERVICE_MENU: list[tuple[str, int, int]] = [
    ("guarantee_letter", 0, 0),
    ("lease_agreement", 0, 2000),
    ("owner_confirmation", 1000, 3000),
    ("door_sign", 1500, 4000),
    ("mail_reception", 900, 2500),
    ("fns_visit_photo", 1200, 3000),
    ("phone_answering", 2500, 6000),
    ("visitor_reception", 2000, 5000),
]


def _photo_files(photo_dir: pathlib.Path) -> list[pathlib.Path]:
    files = sorted(p for p in photo_dir.glob("*.jpg") if p.is_file())
    if not files:
        raise SystemExit(f"В {photo_dir} нет ни одного .jpg — нечего прикреплять")
    return files


def _to_landscape(raw: bytes, ratio: float = 3 / 2) -> bytes:
    """Кадрирует по центру до 3:2.

    В исходном наборе есть и вертикальные снимки: в сетке каталога карточки
    горизонтальные, и вертикальное фото обрезалось бы как попало. Приводим всё
    к одной пропорции, чтобы витрина выглядела единообразно.
    """
    import io

    from PIL import Image

    with Image.open(io.BytesIO(raw)) as img:
        img = img.convert("RGB")
        width, height = img.size
        target = width / ratio
        if target <= height:
            top = int((height - target) / 2)
            box = (0, top, width, int(top + target))
        else:
            target_width = int(height * ratio)
            left = int((width - target_width) / 2)
            box = (left, 0, left + target_width, height)
        buffer = io.BytesIO()
        img.crop(box).save(buffer, format="JPEG", quality=90)
        return buffer.getvalue()


async def _purge(db) -> dict[str, int]:
    """Снимает весь демо-набор: адреса, фото, услуги и собственников."""
    providers = (
        await db.execute(select(Provider).where(Provider.code.like(f"{DEMO_CODE_PREFIX}%")))
    ).scalars().all()
    provider_ids = [p.id for p in providers]
    if not provider_ids:
        return {"providers": 0, "addresses": 0}

    addresses = (
        await db.execute(select(Address).where(Address.provider_id.in_(provider_ids)))
    ).scalars().all()
    address_ids = [a.id for a in addresses]

    if address_ids:
        # Файлы в хранилище не трогаем: они дешёвые, а удаление по одному
        # ключу — лишний риск задеть чужое. Записи снимаем.
        await db.execute(delete(AddressPhoto).where(AddressPhoto.address_id.in_(address_ids)))
        await db.execute(delete(AddressService).where(AddressService.address_id.in_(address_ids)))
        await db.execute(delete(Address).where(Address.id.in_(address_ids)))
    await db.execute(delete(Provider).where(Provider.id.in_(provider_ids)))
    await db.commit()
    return {"providers": len(provider_ids), "addresses": len(address_ids)}


async def _seed(db, *, count: int, photo_dir: pathlib.Path, admin: User) -> dict[str, int]:
    rng = random.Random(20260726)
    photos = _photo_files(photo_dir)
    storage = get_object_storage()

    listings = LISTINGS[:count]
    created = {"providers": 0, "addresses": 0, "photos": 0, "services": 0}

    for index, (city, street, room, fns_number, fns_city) in enumerate(listings):
        code = f"{DEMO_CODE_PREFIX}{index + 1:03d}"
        existing = (
            await db.execute(select(Provider).where(Provider.code == code))
        ).scalar_one_or_none()
        if existing is not None:
            continue

        short_name, full_name = COMPANY_NAMES[index % len(COMPANY_NAMES)]
        signatory, signatory_gen, initials = SIGNATORIES[index % len(SIGNATORIES)]

        provider = Provider(
            code=code,
            short_name=short_name,
            full_name=full_name,
            # Реквизиты заведомо синтетические: контрольные суммы не сходятся,
            # ни с одной действующей организацией пересечься не могут.
            inn=f"77{index + 1:08d}",
            kpp=f"77{index + 1:07d}",
            ogrn=f"1177700{index + 1:06d}",
            legal_address=f"г. {city}, {street}",
            signatory_name=signatory,
            signatory_name_genitive=signatory_gen,
            signatory_initials=initials,
            signatory_position="Генеральный директор",
            signatory_position_genitive="Генерального директора",
            signatory_basis="Устава",
            phone=f"+7 (495) {700 + index:03d}-{10 + index:02d}-{20 + index:02d}",
            is_active=True,
        )
        db.add(provider)
        await db.flush()
        created["providers"] += 1

        price_11m = Decimal(rng.randrange(22_000, 78_000, 1_000))
        price_6m = (price_11m * Decimal("0.62")).quantize(Decimal("1"))
        lat, lon = CITY_COORDS[city]

        address = Address(
            provider_id=provider.id,
            full_address=f"г. {city}, {street}",
            room_number=room,
            cadastral_number=f"{fns_number:02d}:0{index % 9 + 1}:000{index % 7 + 1}00{index % 5 + 1}:{1000 + index}",
            ownership_doc="Выписка из ЕГРН",
            ownership_doc_short="Выписка ЕГРН",
            ownership_doc_pages=rng.randint(2, 5),
            price_6m=price_6m,
            price_11m=price_11m,
            correspondence_price=(
                Decimal(rng.randrange(1_500, 4_500, 500)) if index % 3 != 2 else None
            ),
            fns_number=fns_number,
            fns_city=fns_city,
            # Небольшой разброс вокруг центра города, чтобы метки не слипались.
            latitude=Decimal(str(round(lat + rng.uniform(-0.05, 0.05), 6))),
            longitude=Decimal(str(round(lon + rng.uniform(-0.08, 0.08), 6))),
            is_available=True,
            description=DESCRIPTIONS[index % len(DESCRIPTIONS)],
            notes=f"{DEMO_NOTE_MARKER} витринная карточка, заменить на реальную",
            publication_status=AddressPublicationStatus.PUBLISHED.value,
        )
        db.add(address)
        await db.flush()
        created["addresses"] += 1

        # Услуги: гарантийка есть всегда, остальное вразнобой.
        chosen = [SERVICE_MENU[0]] + rng.sample(SERVICE_MENU[1:], rng.randint(2, 5))
        for kind, low, high in chosen:
            db.add(
                AddressService(
                    address_id=address.id,
                    kind=kind,
                    price=Decimal(low if low == high else rng.randrange(low, high + 1, 100)),
                    is_active=True,
                )
            )
            created["services"] += 1

        # Главное фото — своё у каждой карточки; второе берём со сдвигом.
        picks = [photos[index % len(photos)], photos[(index * 7 + 3) % len(photos)]]
        for order, path in enumerate(dict.fromkeys(picks)):
            processed = process_image_bytes(_to_landscape(path.read_bytes()))
            digest = hashlib.sha256(processed.content).hexdigest()
            key = f"addresses/{address.id}/photos/{digest[:16]}/{path.stem}.jpg"
            stored = storage.put_bytes(
                key=key, content=processed.content, content_type="image/jpeg"
            )
            db.add(
                AddressPhoto(
                    address_id=address.id,
                    storage_backend=stored.backend,
                    storage_key=stored.key,
                    original_filename=f"{path.stem}.jpg",
                    content_type="image/jpeg",
                    size_bytes=len(processed.content),
                    width=processed.width,
                    height=processed.height,
                    sha256=digest,
                    moderation_status=AddressPhotoModerationStatus.APPROVED.value,
                    moderated_by=admin.id,
                    is_main=(order == 0),
                    sort_order=order,
                    uploaded_by=admin.id,
                )
            )
            created["photos"] += 1

        await db.flush()

    await db.commit()
    return created


async def main() -> None:
    parser = argparse.ArgumentParser(description="Витринные собственники и адреса")
    parser.add_argument("--count", type=int, default=25, help="сколько карточек (макс. 25)")
    parser.add_argument(
        "--photos",
        default="scripts/demo_photos",
        help="каталог с исходными .jpg",
    )
    parser.add_argument("--purge", action="store_true", help="снять весь демо-набор и выйти")
    args = parser.parse_args()

    async with AsyncSessionLocal() as db:
        if args.purge:
            removed = await _purge(db)
            print(f"Снято: собственников {removed['providers']}, адресов {removed['addresses']}")
            return

        admin = (
            await db.execute(
                select(User)
                .where(User.role == UserRole.ADMIN.value, User.is_active.is_(True))
                .order_by(User.created_at)
            )
        ).scalars().first()
        if admin is None:
            raise SystemExit("Нет активного администратора — некого указать автором фото")

        created = await _seed(
            db,
            count=min(args.count, len(LISTINGS)),
            photo_dir=pathlib.Path(args.photos),
            admin=admin,
        )
        print(
            "Создано: собственников {providers}, адресов {addresses}, "
            "фото {photos}, услуг {services}".format(**created)
        )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(1)
