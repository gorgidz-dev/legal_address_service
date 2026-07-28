"""Сид справочника fns_offices + бэкфилл addresses.fns_office_id.

Зачем: каскад «Регион → Город → ИФНС» в форме подбора строится эндпоинтом
/marketplace/geo, а тот делает INNER JOIN по addresses.fns_office_id. Пока
справочник пуст, эндпоинт отдаёт [] и три селекта формы стоят пустыми.

Откуда берётся регион. У адреса есть только номер инспекции (fns_number) и
город в дательном падеже (fns_city — форма для гарантийного письма, «по
Екатеринбургу»). Региона нет ни в одном поле, поэтому он восстанавливается по
справочнику городов CITIES ниже; там же лежит код субъекта, из которого
собирается федеральный код инспекции (код субъекта + номер, «6639»).

Прежняя версия скрипта считала весь каталог московским: писала всем офисам
регион и город «Москва» и код 77NN, а адреса привязывала по одному лишь
fns_number. На мультирегиональном каталоге это склеило бы инспекции с
одинаковым номером из разных субъектов в одну запись.

Идемпотентен: офис ищется по коду, у адреса fns_office_id проставляется только
если он пуст.

Запуск локально:  python -m scripts.seed_fns_offices
На проде:         docker compose run --rm backend python -m scripts.seed_fns_offices
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.address import Address
from app.models.fns_office import FnsOffice


@dataclass(frozen=True)
class CityRef:
    """Город каталога: как называется, в каком субъекте и с каким кодом."""

    city: str
    region: str
    # Код субъекта РФ — первые две цифры федерального кода инспекции.
    region_code: str
    # Дательный падеж — в этом виде город лежит в addresses.fns_city.
    dative: str


# Города, которые встречаются в каталоге и в демо-сидах. Список расширяется
# по мере появления новых городов: адрес из города не из списка скрипт не
# трогает и печатает отдельной строкой в отчёте.
CITIES: tuple[CityRef, ...] = (
    CityRef("Москва", "Москва", "77", "Москве"),
    CityRef("Санкт-Петербург", "Санкт-Петербург", "78", "Санкт-Петербургу"),
    CityRef("Казань", "Республика Татарстан", "16", "Казани"),
    CityRef("Краснодар", "Краснодарский край", "23", "Краснодару"),
    CityRef("Екатеринбург", "Свердловская область", "66", "Екатеринбургу"),
    CityRef("Новосибирск", "Новосибирская область", "54", "Новосибирску"),
    CityRef("Нижний Новгород", "Нижегородская область", "52", "Нижнему Новгороду"),
    CityRef("Ростов-на-Дону", "Ростовская область", "61", "Ростову-на-Дону"),
    CityRef("Самара", "Самарская область", "63", "Самаре"),
    CityRef("Челябинск", "Челябинская область", "74", "Челябинску"),
    CityRef("Уфа", "Республика Башкортостан", "02", "Уфе"),
    CityRef("Красноярск", "Красноярский край", "24", "Красноярске"),
    CityRef("Пермь", "Пермский край", "59", "Перми"),
    CityRef("Волгоград", "Волгоградская область", "34", "Волгограде"),
    CityRef("Тюмень", "Тюменская область", "72", "Тюмени"),
    CityRef("Калининград", "Калининградская область", "39", "Калининграде"),
    CityRef("Владивосток", "Приморский край", "25", "Владивостоке"),
    CityRef("Воронеж", "Воронежская область", "36", "Воронеже"),
    CityRef("Химки", "Московская область", "50", "Химках"),
    CityRef("Красногорск", "Московская область", "50", "Красногорске"),
)

_BY_DATIVE = {ref.dative: ref for ref in CITIES}
_BY_NAME = {ref.city: ref for ref in CITIES}

# «г. Нижний Новгород, ул. ...» и «Московская обл., г. Химки, ...» — берём то,
# что стоит между «г.» и следующей запятой.
_CITY_IN_ADDRESS = re.compile(r"\bг\.\s*([^,]+)")


def resolve_city(full_address: str | None, fns_city: str | None) -> CityRef | None:
    """Город адреса: сначала по дательной форме, потом по строке адреса.

    fns_city заполняется при создании адреса и есть почти всегда; разбор
    full_address — запасной путь для адресов, заведённых без него.
    """
    if fns_city:
        ref = _BY_DATIVE.get(fns_city.strip())
        if ref is not None:
            return ref
    match = _CITY_IN_ADDRESS.search(full_address or "")
    if match:
        return _BY_NAME.get(match.group(1).strip())
    return None


def office_code(region_code: str, fns_number: int) -> str:
    """Федеральный код инспекции: код субъекта + двузначный номер."""
    return f"{region_code}{fns_number:02d}"


def office_name(fns_number: int, ref: CityRef, fns_city: str | None) -> str:
    """Человекочитаемое имя. Падежную форму берём из адреса, если она есть."""
    return f"ИФНС России № {fns_number} по {fns_city or ref.dative}"


async def _seed() -> None:
    async with AsyncSessionLocal() as db:
        addresses = list(
            (
                await db.execute(
                    select(Address).where(Address.fns_number.is_not(None))
                )
            )
            .scalars()
            .all()
        )

        created = 0
        linked = 0
        unresolved: list[str] = []
        # Кэш по коду в пределах прогона: один код — одна запись справочника,
        # даже если под него подпадают два города одного субъекта.
        offices: dict[str, FnsOffice] = {}

        for address in addresses:
            ref = resolve_city(address.full_address, address.fns_city)
            if ref is None:
                unresolved.append(
                    f"{address.full_address} (ИФНС {address.fns_number}, "
                    f"город «{address.fns_city or '—'}»)"
                )
                continue

            code = office_code(ref.region_code, address.fns_number)
            office = offices.get(code)
            if office is None:
                office = (
                    await db.execute(
                        select(FnsOffice).where(FnsOffice.code == code)
                    )
                ).scalar_one_or_none()
            if office is None:
                office = FnsOffice(
                    code=code,
                    name=office_name(address.fns_number, ref, address.fns_city),
                    short_number=address.fns_number,
                    region=ref.region,
                    city=ref.city,
                )
                db.add(office)
                await db.flush()
                created += 1
            offices[code] = office

            if address.fns_office_id is None:
                address.fns_office_id = office.id
                linked += 1

        await db.commit()

        print(
            f"fns_offices: создано {created}, адресов привязано {linked}, "
            f"адресов просмотрено {len(addresses)}"
        )
        if unresolved:
            print(f"НЕ РАСПОЗНАН ГОРОД — {len(unresolved)} адрес(ов), добавь их в CITIES:")
            for line in unresolved:
                print(f"  · {line}")


def main() -> None:
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
