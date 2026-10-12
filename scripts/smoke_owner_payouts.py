"""Смоук выплат собственникам: настоящий Postgres + настоящий HTTP-стек.

Юнит-тесты (tests/test_owner_payouts.py) работают на подставной сессии и не
видят SQL. Здесь — то, что видно только на настоящей базе: миграция 0036 и её
CHECK/частичные уникальные индексы, вставка выплаты в той же транзакции, где
автомат Т-Банка переводит платёж в «оплачен», блокировки FOR UPDATE, права
доступа на настоящих сессиях и CSRF.

Банк и ЕГРЮЛ не нужны: статус банка подаётся прямо в автомат
(apply_bank_state), DaData подменена на заглушку с известными ответами.

Запуск — ТОЛЬКО на отдельной пустой базе, в имени которой есть payouts_smoke:
    docker exec uradres-pg createdb -U postgres payouts_smoke
    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/payouts_smoke \\
        .venv/bin/alembic upgrade head
    DATABASE_URL=...payouts_smoke PYTHONPATH=. .venv/bin/python -X utf8 -m scripts.smoke_owner_payouts
После — dropdb.
"""
from __future__ import annotations

import asyncio
import secrets
import sys
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.auth import utcnow
from app.config import settings
from app.database import AsyncSessionLocal
from app.enums import AddressPublicationStatus, ApplicationStatus, PaymentStatus, UserRole
from app.main import app
from app.models.address import Address
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.owner_payout import OwnerPayout
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.user import User
from app.models.user_session import UserSession
from app.routers import owner_payouts as payouts_router
from app.schemas.client import DaDataLookupResponse
from app.services.auth_security import hash_token
from app.services.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.services.owner_payouts import MOSCOW
from app.services.tbank_payments import apply_bank_state, lock_payment

FAILURES: list[str] = []
ADDRESS = "г. Москва, ул. Тверская, д. 7, стр. 1, помещ. 3"
EGRUL_SAME = "125009, г Москва, муниципальный округ Тверской вн.тер.г., ул Тверская, д 7, стр 1, помещ. 3"
EGRUL_OTHER = "101000, г Москва, ул Мясницкая, д 1"
INN_OK, INN_ELSEWHERE = "7707083893", "7736207543"
TERMINAL = "1700000000000"  # не DEMO: выплата заводится только по «настоящим» деньгам


def check(condition: bool, label: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}")
    if not condition:
        FAILURES.append(label)


class FakeDaData:
    """ЕГРЮЛ: два известных ИНН — по адресу заявки и по чужому адресу."""

    def __init__(self, registered_on: date):
        self.registered_on = registered_on
        self.invalidated: list[str] = []

    def invalidate(self, inn: str) -> None:
        self.invalidated.append(inn)

    async def lookup(self, inn: str):
        addresses = {INN_OK: EGRUL_SAME, INN_ELSEWHERE: EGRUL_OTHER}
        if inn not in addresses:
            return None
        return DaDataLookupResponse(
            inn=inn, kpp="770101001", ogrn={INN_OK: "1027700132195", INN_ELSEWHERE: "1027700229193"}[inn],
            full_name='ООО "Новая компания"',
            short_name='ООО "Новая"', legal_address=addresses[inn], kladr_id=None,
            signatory_name=None, signatory_position=None, okved_main_code=None, okved_main_name=None,
            egrul_status="ACTIVE",
            blockers=DaDataLookupResponse.Blockers(
                liquidating_or_liquidated=False, bankrupt=False, signatory_disqualified=False, is_branch=False,
            ),
            registration_date=self.registered_on,
        )


async def seed() -> dict:
    now = utcnow()
    async with AsyncSessionLocal() as db:
        provider = Provider(
            code=f"smoke-pay-{uuid4().hex[:6]}", full_name='ООО "Собственник"', short_name="ООО Собственник",
            inn="7701111111", bank_name="Банк", settlement_account="40702810000000000001",
            corr_account="30101810000000000001", bik="044525000", commission_percent=Decimal("20"),
        )
        other = Provider(code=f"smoke-pay-{uuid4().hex[:6]}", full_name='ООО "Другой"', short_name="ООО Другой")
        db.add_all([provider, other])
        await db.flush()
        address = Address(
            provider_id=provider.id, full_address=ADDRESS, cadastral_number=f"77:01:{uuid4().int % 10**7}:1",
            ownership_doc="Свидетельство", ownership_doc_short="Св-во", ownership_doc_pages=1,
            price_6m=Decimal("18000"), price_11m=Decimal("30000"),
            publication_status=AddressPublicationStatus.PUBLISHED.value, is_available=True,
        )
        users = {
            "admin": User(email="smoke-pay-admin@example.com", full_name="Админ", role=UserRole.ADMIN.value),
            "client": User(email="smoke-pay-client@example.com", full_name="Клиент", role=UserRole.CLIENT.value),
            "stranger": User(email="smoke-pay-stranger@example.com", full_name="Чужой", role=UserRole.CLIENT.value),
            "owner": User(email="smoke-pay-owner@example.com", full_name="Собственник", role=UserRole.OWNER.value, provider_id=provider.id),
            "other_owner": User(email="smoke-pay-other@example.com", full_name="Другой", role=UserRole.OWNER.value, provider_id=other.id),
        }
        db.add(address)
        db.add_all(users.values())
        await db.flush()

        apps, payments = [], []
        for n in range(3):
            application = Application(
                type="initial_registration", status=ApplicationStatus.AWAITING_PAYMENT.value,
                provider_id=provider.id, address_id=address.id, company_name=f"Смоук-выплата-{n}",
                planned_client_name=f"Смоук-выплата-{n}", contact_name="Клиент", contact_phone="+79001234567",
                contact_email=users["client"].email, term_months=11, has_correspondence_service=False,
                created_by=users["client"].id,
            )
            db.add(application)
            await db.flush()
            payment = Payment(
                application_id=application.id, provider="tbank", payer_type="individual",
                status=PaymentStatus.AWAITING_USER.value, amount_kopeks=3_000_000, currency="RUB",
                pay_for="application", provider_payment_id=str(9_500_000_000 + n), provider_status="NEW",
                provider_account=TERMINAL, initiated_by=users["client"].id,
            )
            db.add(payment)
            apps.append(application)
            payments.append(payment)
        await db.flush()

        tokens = {}
        for key, user in users.items():
            raw = secrets.token_urlsafe(32)
            db.add(UserSession(
                user_id=user.id, token_hash=hash_token(raw), expires_at=now + timedelta(hours=2),
                created_at=now, session_type="web",
            ))
            tokens[key] = raw
        await db.commit()
        return {
            "apps": [str(a.id) for a in apps], "payments": [str(p.id) for p in payments],
            "tokens": tokens, "provider": str(provider.id), "other": str(other.id),
            "created": apps[0].created_at.date(),
        }


async def bank_confirms(payment_id: str) -> None:
    """Как уведомление банка: под блокировкой платежа автомат получает CONFIRMED."""
    async with AsyncSessionLocal() as db:
        payment = await lock_payment(db, UUID(payment_id))
        await apply_bank_state(db, payment=payment, status="CONFIRMED", amount_kopeks=payment.amount_kopeks)
        await db.commit()


async def set_app_status(application_id: str, status: ApplicationStatus) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(Application).where(Application.id == UUID(application_id)).values(status=status.value))
        await db.commit()


async def payout_for(application_id: str) -> OwnerPayout | None:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                select(OwnerPayout).where(OwnerPayout.application_id == UUID(application_id))
                .order_by(OwnerPayout.created_at.desc())
            )
        ).scalars().first()


async def owner_titles(application_id: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(ApplicationEvent.title).where(
                ApplicationEvent.application_id == UUID(application_id), ApplicationEvent.audience == "owner"
            )
        )
        return list(rows.scalars())


async def run_checks() -> None:
    ids = await seed()
    apps, pays, tokens = ids["apps"], ids["payments"], ids["tokens"]
    fake = FakeDaData(registered_on=ids["created"] + timedelta(days=5))
    payouts_router.get_dadata_service = lambda: fake  # type: ignore[assignment]
    csrf = secrets.token_urlsafe(16)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://smoke", headers={CSRF_HEADER_NAME: csrf}
    ) as http:

        def login_as(who: str) -> None:
            http.cookies.clear()
            http.cookies.set(settings.session_cookie_name, tokens[who])
            http.cookies.set(CSRF_COOKIE_NAME, csrf)

        print("\n== оплата заводит выплату (автомат Т-Банка, настоящий INSERT) ==")
        await bank_confirms(pays[0])
        payout = await payout_for(apps[0])
        check(payout is not None, "выплата заведена в той же транзакции, что и оплата")
        check(payout.status == "awaiting_registration", f"ждёт регистрации ({payout.status})")
        check((payout.commission_kopeks, payout.payout_kopeks) == (600_000, 2_400_000),
              f"20% от 30 000 ₽: 6 000 комиссия, 24 000 собственнику ({payout.commission_kopeks}, {payout.payout_kopeks})")
        await bank_confirms(pays[0])  # повтор уведомления
        async with AsyncSessionLocal() as db:
            n = len((await db.execute(select(OwnerPayout).where(OwnerPayout.application_id == UUID(apps[0])))).scalars().all())
        check(n == 1, "повтор банка не плодит вторую выплату")

        print("\n== права доступа ==")
        login_as("owner")
        r = await http.get("/api/v1/payouts")
        check(r.status_code == 403, f"собственнику реестр админа закрыт ({r.status_code})")
        r = await http.get("/api/v1/payouts/mine")
        check(r.status_code == 200 and r.json() == [], "оплаченная, но ещё не назначенная заявка собственнику не видна")
        await set_app_status(apps[0], ApplicationStatus.ASSIGNED_TO_OWNER)
        r = await http.get("/api/v1/payouts/mine")
        mine = r.json()
        check(r.status_code == 200 and len(mine) == 1 and mine[0]["payout_kopeks"] == 2_400_000, "собственник видит свою выплату")
        check("payee" not in mine[0] and "blockers" not in mine[0], "в ответе собственнику нет внутренних полей")
        login_as("other_owner")
        r = await http.get("/api/v1/payouts/mine")
        check(r.status_code == 200 and r.json() == [], "чужой собственник чужих выплат не видит")
        r = await http.patch(f"/api/v1/providers/{ids['provider']}/payout-settings", json={"commission_percent": "1"})
        check(r.status_code == 403, f"собственник не меняет себе процент ({r.status_code})")

        print("\n== клиент сообщает ИНН ==")
        login_as("client")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/inn", json={"inn": INN_OK})
        check(r.status_code == 409, f"до выдачи документов — рано ({r.status_code})")
        await set_app_status(apps[0], ApplicationStatus.READY_FOR_CLIENT)
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/inn", json={"inn": "123"})
        check(r.status_code == 422, f"кривой ИНН — 422 ({r.status_code})")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/inn", json={"inn": INN_OK})
        check(r.status_code == 200 and r.json()["registration_inn"] == INN_OK, f"ИНН принят ({r.status_code})")
        login_as("stranger")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/inn", json={"inn": INN_OK})
        check(r.status_code == 404, f"чужой клиент — 404 ({r.status_code})")
        login_as("owner")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/confirm", json={"inn": INN_OK})
        check(r.status_code == 403, f"собственник сам себе регистрацию не подтверждает ({r.status_code})")

        print("\n== админ сверяет с ЕГРЮЛ и подтверждает ==")
        login_as("admin")
        r = await http.get("/api/v1/payouts", params={"status": "awaiting_registration"})
        row = next((x for x in r.json() if x["application_id"] == apps[0]), None)
        check(row is not None and row["suggested_inn"] == INN_OK, "в реестре ИНН от клиента подставлен")
        check(row is not None and row["payee"]["settlement_account"] == "40702810000000000001", "реквизиты собственника в реестре")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/check", json={"inn": INN_ELSEWHERE})
        body = r.json()
        check(r.status_code == 200 and body["address_matches"] is False and body["warnings"], "чужой адрес — подсказка «не совпал»")
        check(INN_ELSEWHERE in fake.invalidated, "кэш DaData сброшен перед сверкой")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/confirm", json={"inn": INN_ELSEWHERE})
        check(r.status_code == 409, f"несовпавший адрес без ручной отметки — 409 ({r.status_code})")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/confirm", json={"inn": "7728168971"})  # верный ИНН, но в подставном ЕГРЮЛ его нет
        check(r.status_code == 409, f"ИНН нет в ЕГРЮЛ — 409 ({r.status_code})")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/confirm", json={"inn": INN_OK})
        check(r.status_code == 200 and (r.json().get("payout") or {}).get("status") == "due", f"подтверждено → к выплате ({r.status_code} {r.text[:150]})")
        r = await http.post(f"/api/v1/payouts/applications/{apps[0]}/registration/confirm", json={"inn": INN_OK})
        check(r.status_code == 409, f"второе подтверждение — 409 ({r.status_code})")
        async with AsyncSessionLocal() as db:
            application = await db.get(Application, UUID(apps[0]))
        check(application.registration_check["address_matches"] is True, "снимок сверки сохранён в заявке")
        check("Регистрация подтверждена — выплата в очереди" in await owner_titles(apps[0]), "собственнику сообщили")

        print("\n== отметка выплаты ==")
        payout_id = str((await payout_for(apps[0])).id)
        r = await http.post(f"/api/v1/payouts/{payout_id}/mark-paid", json={"paid_on": date.today().isoformat(), "bank_reference": ""})
        check(r.status_code == 422, f"без номера платёжки — 422 ({r.status_code})")
        tomorrow = (utcnow().astimezone(MOSCOW).date() + timedelta(days=1)).isoformat()  # даты платёжек — по Москве
        r = await http.post(f"/api/v1/payouts/{payout_id}/mark-paid", json={"paid_on": tomorrow, "bank_reference": "15"})
        check(r.status_code == 409, f"дата в будущем — 409 ({r.status_code})")
        today = utcnow().astimezone(MOSCOW).date().isoformat()
        r1, r2 = await asyncio.gather(
            http.post(f"/api/v1/payouts/{payout_id}/mark-paid", json={"paid_on": today, "bank_reference": "15"}),
            http.post(f"/api/v1/payouts/{payout_id}/mark-paid", json={"paid_on": today, "bank_reference": "16"}),
        )
        codes = sorted([r1.status_code, r2.status_code])
        check(codes == [200, 409], f"два одновременных «выплачено» — одно проходит ({codes})")
        paid = await payout_for(apps[0])
        check(paid.status == "paid" and paid.payee and paid.payee["bik"] == "044525000", "выплачено, реквизиты зафиксированы")
        r = await http.post(f"/api/v1/payouts/{payout_id}/cancel", json={"reason": "передумали"})
        check(r.status_code == 409, f"выплаченное не отменить ({r.status_code})")
        check("Выплата отправлена" in await owner_titles(apps[0]), "собственнику сообщили о переводе")

        print("\n== возврат клиенту блокирует и отменяет ==")
        await bank_confirms(pays[1])
        await set_app_status(apps[1], ApplicationStatus.REFUND_PENDING)
        r = await http.post(f"/api/v1/payouts/applications/{apps[1]}/registration/confirm", json={"inn": INN_OK})
        check(r.status_code == 409, f"возврат в пути — подтверждать нельзя ({r.status_code})")
        r = await http.get("/api/v1/payouts", params={"status": "awaiting_registration"})
        row = next((x for x in r.json() if x["application_id"] == apps[1]), None)
        check(row is not None and row["blockers"], "в реестре видна причина блокировки")
        pid = str((await payout_for(apps[1])).id)
        r = await http.post(f"/api/v1/payouts/{pid}/cancel", json={"reason": "Возврат клиенту"})
        check(r.status_code == 200 and r.json()["status"] == "cancelled", f"отменена ({r.status_code})")
        await set_app_status(apps[1], ApplicationStatus.COMPLETED)
        r = await http.post(f"/api/v1/payouts/applications/{apps[1]}/registration/check", json={"inn": INN_OK})
        check(any("уже подтверждён" in w for w in r.json().get("warnings", [])), "предупреждение: ИНН уже подтверждён по другой заявке")
        r = await http.post(f"/api/v1/payouts/applications/{apps[1]}/registration/confirm", json={"inn": INN_OK})
        check(r.status_code == 409 and "отменили" in r.text, f"отменённую выплату подтверждение не переоткрывает — 409, а не 500 ({r.status_code})")

        print("\n== процент собственника и ограничения базы ==")
        r = await http.patch(f"/api/v1/providers/{ids['provider']}/payout-settings", json={"commission_percent": "12.5"})
        check(r.status_code == 200 and Decimal(r.json()["effective_percent"]) == Decimal("12.5"), f"админ задал 12,5% ({r.status_code})")
        r = await http.patch(f"/api/v1/providers/{ids['provider']}/payout-settings", json={"commission_percent": "100"})
        check(r.status_code == 422, f"100% — 422 ({r.status_code})")
        r = await http.patch(f"/api/v1/providers/{ids['other']}/payout-settings", json={
            "bank_name": "АО Банк", "settlement_account": "40702810900000000002",
            "corr_account": "30101810400000000225", "bik": "044525225",
        })
        body = r.json()
        check(r.status_code == 200 and body["bik"] == "044525225" and body["commission_percent"] is None,
              f"реквизиты заданы, процент не тронут ({r.status_code})")
        r = await http.patch(f"/api/v1/providers/{ids['other']}/payout-settings", json={"bik": "12"})
        check(r.status_code == 422, f"кривой БИК — 422 ({r.status_code})")
        await bank_confirms(pays[2])
        third = await payout_for(apps[2])
        check(third.commission_percent == Decimal("12.5") and third.payout_kopeks == 2_625_000, "новая оплата — по новому проценту")
        check((await payout_for(apps[0])).commission_percent == Decimal("20"), "старая выплата сохранила свой процент")

        async def extra_payment(application_id: str) -> UUID:
            """Ещё один оплаченный платёж по заявке — чтобы базу проверял только нужный индекс."""
            async with AsyncSessionLocal() as db:
                p = Payment(
                    application_id=UUID(application_id), provider="tbank", payer_type="individual",
                    status=PaymentStatus.SUCCEEDED.value, amount_kopeks=1000, currency="RUB",
                    pay_for="application", provider_payment_id=str(9_600_000_000 + secrets.randbelow(10**6)),
                    provider_account=TERMINAL,
                )
                db.add(p)
                await db.commit()
                return p.id

        async def rejected(payout: OwnerPayout) -> bool:
            async with AsyncSessionLocal() as db:
                db.add(payout)
                try:
                    await db.flush()
                    return False
                except IntegrityError:
                    return True
                finally:
                    await db.rollback()

        check(await rejected(OwnerPayout(
            application_id=UUID(apps[2]), payment_id=await extra_payment(apps[2]), provider_id=third.provider_id,
            status="awaiting_registration", gross_kopeks=1000,
        )), "вторая живая выплата на заявку отвергнута базой")
        # По заявке apps[1] выплата отменена — новая живая допустима; ломаем только суммы.
        check(await rejected(OwnerPayout(
            application_id=UUID(apps[1]), payment_id=await extra_payment(apps[1]), provider_id=third.provider_id,
            status="due", gross_kopeks=1000, commission_percent=Decimal("10"),
            commission_kopeks=100, payout_kopeks=901,
        )), "несходящиеся суммы отвергнуты базой")
        check(not await rejected(OwnerPayout(
            application_id=UUID(apps[1]), payment_id=await extra_payment(apps[1]), provider_id=third.provider_id,
            status="awaiting_registration", gross_kopeks=1000,
        )), "после отмены можно завести новую выплату по той же заявке")

async def main() -> int:
    if "payouts_smoke" not in settings.database_url:
        print("Отказ: скрипт пишет данные и запускается только на базе payouts_smoke.")
        return 2
    await run_checks()
    print("\n" + ("ВСЁ ЗЕЛЁНОЕ" if not FAILURES else f"ПРОВАЛЫ: {FAILURES}"))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
