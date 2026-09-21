"""Боевой прогон оплаты через Т-Банк: настоящая база + живой DEMO-терминал.

Запускается ТОЛЬКО против отдельной пустой базы (DATABASE_URL=...tbank_smoke) и
только с DEMO-терминалом — первым делом в этом убеждается. Нужны переменные:
PAYMENT_PROVIDER=tbank, TBANK_TERMINAL_KEY=...DEMO, TBANK_PASSWORD,
TBANK_TEST_PAYER_EMAILS=smoke-tbank-client@example.com и
TBANK_NOTIFICATION_URL на заглушку (уведомления банка по тестовым заказам
не должны уходить на прод).

Зачем при сотне юнит-тестов: они работают на подставной сессии и не видят SQL.
Здесь проверяется то, что видно только на настоящем Postgres — миграция 0034,
частичные уникальные индексы, FOR UPDATE / SKIP LOCKED при одновременных
запросах, вставка событий — плюс настоящий HTTP-стек (middleware, публичный
путь) и настоящий банк (Init, GetState, Cancel через TLS с сертификатами Минцифры).

Уведомления имитируются: подписываем их паролем DEMO-терминала, как банк. А
вот решение приёмник принимает по ЖИВОМУ GetState. Оплатить заказ на DEMO
можно только руками на форме, поэтому для «оплаченных» платежей ответ банка
подменяется (BANK_OVERRIDE, только по перечисленным PaymentId) — это честно
помечено в выводе словом «подмена».
"""
from __future__ import annotations

import asyncio
import json
import secrets
import sys
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, update

from app.auth import utcnow
from app.config import settings
from app.database import AsyncSessionLocal
from app.enums import AddressPublicationStatus, ApplicationStatus, PaymentStatus, UserRole
from app.main import app
from app.models.address import Address
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.incoming_webhook import IncomingWebhook
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_security import hash_token
from app.services.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.services.tbank_acquiring import (
    TBankCancelResult,
    TBankService,
    TBankState,
    get_tbank_service,
    make_token,
)

FAILURES: list[str] = []
CLIENT_EMAIL = "smoke-tbank-client@example.com"
NOTIFY = "/api/v1/webhooks/tbank/notification"
JSON = {"Content-Type": "application/json"}

# ------------------------------------------------------------------
# Подмена ответов банка для конкретных PaymentId (всё прочее — живой банк)
# ------------------------------------------------------------------

BANK_OVERRIDE: dict[str, dict] = {}
CANCEL_CALLS: list[dict] = []
_real_get_state = TBankService.get_state
_real_cancel = TBankService.cancel


async def _get_state(self, *, payment_id):
    override = BANK_OVERRIDE.get(str(payment_id), {})
    if "state" in override:
        status, amount = override["state"]
        return TBankState(payment_id=str(payment_id), status=status, amount_kopeks=amount)
    return await _real_get_state(self, payment_id=payment_id)


async def _cancel(self, **kw):
    override = BANK_OVERRIDE.get(str(kw["payment_id"]), {})
    if "cancel" in override:
        CANCEL_CALLS.append(kw)
        await asyncio.sleep(0.3)  # банк отвечает не сразу — второй клик успеет упереться в блокировку
        return TBankCancelResult(status=override["cancel"], original_amount_kopeks=None, new_amount_kopeks=None)
    return await _real_cancel(self, **kw)


TBankService.get_state = _get_state
TBankService.cancel = _cancel


def check(condition: bool, label: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}")
    if not condition:
        FAILURES.append(label)


def signed(payment: dict, **fields) -> dict:
    """Уведомление в том виде, в каком его шлёт банк: JSON + Token по паролю терминала."""
    body = {
        "TerminalKey": settings.tbank_terminal_key,
        "OrderId": payment["id"],
        "Success": True,
        "Status": "CONFIRMED",
        "PaymentId": int(payment["provider_payment_id"]),
        "ErrorCode": "0",
        "Amount": payment["amount_kopeks"],
        "Pan": "430000******0777",
        "ExpDate": "1129",
        "CardId": 322264,
    }
    body.update(fields)
    body["Token"] = make_token(body, settings.tbank_password)
    return body


async def seed() -> dict:
    async with AsyncSessionLocal() as db:
        provider = Provider(code=f"smoke-{uuid4().hex[:8]}", full_name='ООО "Смоук"', short_name="ООО Смоук")
        db.add(provider)
        await db.flush()
        address = Address(
            provider_id=provider.id,
            full_address="г. Москва, ул. Смоуковая, д. 1",
            cadastral_number="77:01:0001001:1",
            ownership_doc="Свидетельство",
            ownership_doc_short="Св-во",
            ownership_doc_pages=1,
            price_6m=Decimal("30000"),
            price_11m=Decimal("45000"),
            publication_status=AddressPublicationStatus.PUBLISHED.value,
            is_available=True,
        )
        # Почта подтверждена: на DEMO-терминале платить можно только подтвердившим.
        client = User(
            email=CLIENT_EMAIL, full_name="Клиент Смоукин", role=UserRole.CLIENT.value,
            email_verified_at=utcnow(),
        )
        # Обычный клиент: не тестировщик — на DEMO платить не может.
        stranger = User(email="smoke-tbank-stranger@example.com", full_name="Прохожий", role=UserRole.CLIENT.value)
        admin = User(email="smoke-tbank-admin@example.com", full_name="Админ", role=UserRole.ADMIN.value)
        db.add_all([address, client, stranger, admin])
        await db.flush()

        applications = []
        for n, owner in enumerate([client] * 5 + [stranger]):
            application = Application(
                type="initial_registration",
                status=ApplicationStatus.AWAITING_PAYMENT.value,
                provider_id=provider.id,
                address_id=address.id,
                company_name=f"Смоук-{n}",
                planned_client_name=f"Смоук-{n}",
                contact_name=owner.full_name,
                contact_phone="+79001234567",
                contact_email=owner.email,
                term_months=11,
                has_correspondence_service=False,
                created_by=owner.id,
            )
            db.add(application)
            applications.append(application)
        await db.flush()

        tokens = {}
        now = utcnow()
        for key, user in (("client", client), ("stranger", stranger), ("admin", admin)):
            raw = secrets.token_urlsafe(32)
            db.add(UserSession(
                user_id=user.id, token_hash=hash_token(raw),
                expires_at=now + timedelta(hours=2), created_at=now, session_type="web",
            ))
            tokens[key] = raw
        await db.commit()
        return {"applications": [str(a.id) for a in applications], "tokens": tokens}


async def count(model, *conditions) -> int:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one()


async def load_payment(payment_id: str) -> Payment:
    async with AsyncSessionLocal() as db:
        return await db.get(Payment, UUID(payment_id))


async def load_application(application_id: str) -> Application:
    async with AsyncSessionLocal() as db:
        return await db.get(Application, UUID(application_id))


async def age_payment(payment_id: str, **values) -> None:
    """«Прошло время»: сдвинуть отметки платежа в прошлое."""
    async with AsyncSessionLocal() as db:
        await db.execute(update(Payment).where(Payment.id == UUID(payment_id)).values(**values))
        await db.commit()


async def paid_events(application_id: str) -> int:
    return await count(
        ApplicationEvent, ApplicationEvent.application_id == UUID(application_id),
        ApplicationEvent.title == "Оплата получена",
    )


async def run_checks() -> None:
    ids = await seed()
    apps, tokens = ids["applications"], ids["tokens"]
    csrf = secrets.token_urlsafe(16)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://smoke", headers={CSRF_HEADER_NAME: csrf}
    ) as http:

        def login_as(who: str) -> None:
            http.cookies.clear()
            http.cookies.set(settings.session_cookie_name, tokens[who])
            http.cookies.set(CSRF_COOKIE_NAME, csrf)

        async def notify(body: dict):
            http.cookies.clear()  # банк приходит без сессии
            return await http.post(NOTIFY, content=json.dumps(body), headers=JSON)

        print("\n== создание платежа (живой Init) ==")
        login_as("client")
        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[0]})
        check(r.status_code == 201, f"клиент получил ссылку на оплату ({r.status_code} {r.text[:200]})")
        pay0 = r.json()
        check(pay0["provider"] == "tbank", "провайдер tbank")
        check((pay0.get("payment_url") or "").startswith("https://pay.tbank.ru/"), "ссылка на форму Т-Банка")
        check(bool(pay0.get("provider_payment_id")), "PaymentId банка сохранён строкой")
        check(pay0["amount_kopeks"] == 4_500_000, f"сумма 45 000 ₽ в копейках ({pay0['amount_kopeks']})")
        check((await load_payment(pay0["id"])).provider_account == settings.tbank_terminal_key, "терминал записан в платёж")

        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[0]})
        check(r.json()["id"] == pay0["id"], "повторное «Оплатить» отдаёт ту же ссылку")

        live = await get_tbank_service().get_state(payment_id=pay0["provider_payment_id"])
        check(live.order_id == pay0["id"], f"живой GetState отдаёт OrderId = наш id ({live.order_id})")

        print("\n== три одновременных «Оплатить» по одной заявке ==")
        results = await asyncio.gather(*[
            http.post("/api/v1/payments/initiate", json={"application_id": apps[1]}) for _ in range(3)
        ])
        codes = sorted(x.status_code for x in results)
        payment_ids = {x.json().get("id") for x in results if x.status_code in (200, 201)}
        active = await count(
            Payment, Payment.application_id == UUID(apps[1]),
            Payment.status.in_(["pending", "awaiting_user"]),
        )
        check(active == 1, f"в базе ровно один активный платёж (коды {codes})")
        check(len(payment_ids) == 1, "все три ответа — один и тот же платёж")
        pay1 = results[0].json()

        print("\n== DEMO-гард на настоящем HTTP ==")
        login_as("stranger")
        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[5]})
        check(r.status_code == 403, f"обычный клиент на DEMO — 403 ({r.status_code})")
        login_as("admin")
        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[5]})
        check(r.status_code == 201, f"админ создал ссылку за клиента ({r.status_code})")
        pay5 = r.json()
        login_as("stranger")
        r = await http.get(f"/api/v1/payments/{pay5['id']}")
        check(r.status_code == 200 and r.json()["payment_url"] is None, "клиент не видит DEMO-ссылку в GET")
        r = await http.get(f"/api/v1/payments/by-application/{apps[5]}")
        check(r.status_code == 200 and r.json()["payment_url"] is None, "…и в by-application")

        print("\n== уведомление: решает живой GetState, а не тело ==")
        body = signed(pay0)
        r = await notify(body)
        check(r.status_code == 200 and r.text == "OK", f"банку ответили ровно OK ({r.status_code} {r.text!r})")
        payment = await load_payment(pay0["id"])
        check(payment.status == PaymentStatus.AWAITING_USER.value,
              f"подписанное «CONFIRMED» при живом NEW — не засчитано ({payment.status})")
        check(payment.provider_status == "NEW", f"статус — из банка ({payment.provider_status})")
        check((await load_application(apps[0])).status == ApplicationStatus.AWAITING_PAYMENT.value, "заявка ждёт оплату")

        print("\n== оплата (подмена GetState: CONFIRMED) ==")
        BANK_OVERRIDE[pay0["provider_payment_id"]] = {"state": ("CONFIRMED", pay0["amount_kopeks"])}
        body = signed(pay0, Pan="430000******0778")  # следующее уведомление банка
        r = await notify(body)
        check(r.text == "OK", "OK")
        payment = await load_payment(pay0["id"])
        check(payment.status == PaymentStatus.SUCCEEDED.value, f"платёж succeeded ({payment.status})")
        check((await load_application(apps[0])).status == ApplicationStatus.PAID.value, "заявка paid")
        check("ExpDate" not in (payment.last_callback_payload or {}), "срок карты не сохранён")
        check(await paid_events(apps[0]) == 1, "клиенту одно событие «Оплата получена»")
        r = await notify(body)
        check(r.text == "OK", "повтор банка — снова OK")
        check(await paid_events(apps[0]) == 1, "повтор не задвоил событие")
        stored = await count(IncomingWebhook, IncomingWebhook.provider == "tbank")
        check(stored == 2, f"в журнале два разных уведомления ({stored})")

        print("\n== три уведомления разом (FOR UPDATE на Postgres; подмена GetState) ==")
        BANK_OVERRIDE[pay1["provider_payment_id"]] = {"state": ("CONFIRMED", pay1["amount_kopeks"])}
        both = await asyncio.gather(*[notify(signed(pay1, Status=s)) for s in ("AUTHORIZED", "CONFIRMED", "AUTHORIZED")])
        check(all(x.status_code == 200 and x.text == "OK" for x in both), "на все три — OK")
        payment = await load_payment(pay1["id"])
        check(payment.status == PaymentStatus.SUCCEEDED.value, f"итог succeeded ({payment.status})")
        check(await paid_events(apps[1]) == 1, "одно событие об оплате, а не три")

        print("\n== подделки ==")
        forged = signed(pay0, Status="REFUNDED")
        forged["Amount"] = 1
        r = await notify(forged)
        check(r.status_code == 403, f"подменённая сумма — 403 ({r.status_code})")
        r = await notify(dict(signed(pay0), TerminalKey="0000000000DEMO"))
        check(r.status_code == 403, f"чужой терминал — 403 ({r.status_code})")
        genuine = signed(pay0, Status="PARTIAL_REFUNDED")
        shifted = dict(genuine, PaymentId=f"{pay0['provider_payment_id']}PARTIAL_", Status="REFUNDED")
        check(shifted["Token"] == make_token(shifted, settings.tbank_password), "сдвиг границ проходит подпись")
        r = await notify(shifted)
        check(r.text == "OK", "на сдвиг границ — OK (сигнал принят)")
        payment = await load_payment(pay0["id"])
        check(payment.status == PaymentStatus.SUCCEEDED.value, f"«полного возврата» нет — банк не подтвердил ({payment.status})")

        print("\n== сверка при чтении платежа (живой GetState) ==")
        login_as("client")
        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[2]})
        pay2 = r.json()
        await age_payment(pay2["id"], created_at=utcnow() - timedelta(minutes=5))
        r = await http.get(f"/api/v1/payments/{pay2['id']}")
        check(r.status_code == 200, f"клиент читает платёж ({r.status_code})")
        payment = await load_payment(pay2["id"])
        check(payment.provider_checked_at is not None, "сходили к банку за статусом")
        check(payment.provider_status == "NEW", f"банк: NEW ({payment.provider_status})")
        checked_at = payment.provider_checked_at
        await asyncio.gather(*[http.get(f"/api/v1/payments/{pay2['id']}") for _ in range(5)])
        check((await load_payment(pay2["id"])).provider_checked_at == checked_at, "повторные опросы не дёргают банк")

        print("\n== отмена админом (живые GetState + Cancel) ==")
        login_as("admin")
        r = await http.post(f"/api/v1/payments/{pay2['id']}/cancel")
        check(r.status_code == 200, f"админ отменил ({r.status_code} {r.text[:200]})")
        payment = await load_payment(pay2["id"])
        check(payment.status == PaymentStatus.CANCELLED.value, f"платёж cancelled ({payment.status})")
        check(payment.provider_status == "CANCELED", f"у банка CANCELED ({payment.provider_status})")

        print("\n== новая ссылка после отмены ==")
        login_as("client")
        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[2]})
        check(r.status_code == 201 and r.json()["id"] != pay2["id"], "клиент получил новую ссылку")

        print("\n== просроченная ссылка: живой Cancel старой, новая ссылка ==")
        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[4]})
        pay4 = r.json()
        await age_payment(pay4["id"], created_at=utcnow() - timedelta(days=2), expires_at=utcnow() - timedelta(days=1))
        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[4]})
        check(r.status_code == 201 and r.json()["id"] != pay4["id"], f"выдана новая ссылка ({r.status_code})")
        old = await load_payment(pay4["id"])
        check(old.status == PaymentStatus.EXPIRED.value, f"старая закрыта ({old.status}, банк {old.provider_status})")

        print("\n== возврат: только полный, двойной клик — один ключ (подмена Cancel) ==")
        login_as("admin")
        BANK_OVERRIDE[pay0["provider_payment_id"]]["cancel"] = "ASYNC_REFUNDING"
        r = await http.post(f"/api/v1/payments/{pay0['id']}/refund", json={"reason": "частично", "value_refund_kopeks": 100_000})
        check(r.status_code == 422, f"частичный — в ЛК, 422 ({r.status_code})")
        both = await asyncio.gather(*[
            http.post(f"/api/v1/payments/{pay0['id']}/refund", json={"reason": "Отказ налоговой"}) for _ in range(2)
        ])
        check(all(x.status_code == 200 for x in both), f"оба клика — 200 ({[x.status_code for x in both]})")
        keys = [c.get("external_request_id") for c in CANCEL_CALLS]
        check(len(keys) == 2 and len(set(keys)) == 1 and keys[0] == f"refund:{pay0['id']}:1",
              f"оба запроса — один ключ идемпотентности ({keys})")
        check(all("amount_kopeks" not in c for c in CANCEL_CALLS), "без Amount — банк сам соберёт чек возврата")
        payment = await load_payment(pay0["id"])
        check(payment.status == PaymentStatus.REFUND_REQUESTED.value, f"возврат в пути ({payment.status})")

        BANK_OVERRIDE[pay0["provider_payment_id"]]["state"] = ("REFUNDED", pay0["amount_kopeks"])
        await age_payment(
            pay0["id"], created_at=utcnow() - timedelta(minutes=10),
            provider_checked_at=utcnow() - timedelta(minutes=5),
        )
        r = await http.get(f"/api/v1/payments/{pay0['id']}")
        check(r.json()["status"] == PaymentStatus.REFUNDED.value, f"сверка довела до refunded ({r.json()['status']})")
        check(r.json()["refunded_kopeks"] == pay0["amount_kopeks"], "возвращено всё")

        print("\n== фоновая сверка (scripts.reconcile_tbank_payments; подмена GetState) ==")
        from scripts.reconcile_tbank_payments import _run as reconcile

        login_as("client")
        r = await http.post("/api/v1/payments/initiate", json={"application_id": apps[3]})
        pay3 = r.json()
        await age_payment(pay3["id"], created_at=utcnow() - timedelta(minutes=30))
        BANK_OVERRIDE[pay3["provider_payment_id"]] = {"state": ("CONFIRMED", pay3["amount_kopeks"])}
        moved = await reconcile(limit=50)
        check((await load_payment(pay3["id"])).status == PaymentStatus.SUCCEEDED.value,
              f"потерянное уведомление подобрано сверкой ({dict(moved)})")
        check((await load_application(apps[3])).status == ApplicationStatus.PAID.value, "заявка paid")
        moved = await reconcile(limit=50)
        check(sum(moved.values()) == 0, f"второй запуск банк не дёргает ({dict(moved)})")


async def main() -> int:
    if "tbank_smoke" not in settings.database_url:
        print("Отказ: скрипт пишет данные и запускается только на базе tbank_smoke.")
        return 2
    if not settings.tbank_terminal_key.upper().endswith("DEMO"):
        print("Отказ: только DEMO-терминал — боевой списывал бы настоящие деньги.")
        return 2
    if settings.payment_provider != "tbank":
        print("Отказ: нужен PAYMENT_PROVIDER=tbank.")
        return 2
    print(f"окружение: APP_ENV={settings.app_env} терминал=…{settings.tbank_terminal_key[-8:]}")
    await run_checks()
    print("\n" + ("ВСЁ ЗЕЛЁНОЕ" if not FAILURES else f"ПРОВАЛЫ: {FAILURES}"))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
