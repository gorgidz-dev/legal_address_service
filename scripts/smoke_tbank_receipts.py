"""Смоук чеков 54-ФЗ на настоящем Postgres: предоплата в Init → оплата → выдача
документов → закрывающий чек, плюс все аварийные ветки закрывающего чека.

Транспорт Т-Банка здесь ПОДМЕНЁН (FakeBank ниже): проверяется наш код — SQL
захвата отправки (условный UPDATE), FOR UPDATE при постановке в очередь,
миграция 0035, HTTP-стек, эндпоинт действий по заявке и фоновая задача после
коммита. Что банк примет формат Receipt — проверяет scripts/smoke_tbank.py на
живом DEMO-терминале.

Запуск только на отдельной базе tbank_smoke:
    DATABASE_URL=...tbank_smoke PAYMENT_PROVIDER=tbank TBANK_RECEIPTS_ENABLED=true \\
    TBANK_TERMINAL_KEY=...DEMO TBANK_PASSWORD=... TBANK_TEST_PAYER_EMAILS=smoke-rcpt-client@example.com \\
    python -m scripts.smoke_tbank_receipts
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
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.user import User
from app.models.user_session import UserSession
from app.services import tbank_acquiring as ta
from app.services import tbank_receipts
from app.services.auth_security import hash_token
from app.services.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.services.tbank_acquiring import make_token

FAILURES: list[str] = []
CLIENT_EMAIL = "smoke-rcpt-client@example.com"
NOTIFY = "/api/v1/webhooks/tbank/notification"
JSON = {"Content-Type": "application/json"}


def check(condition: bool, label: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}")
    if not condition:
        FAILURES.append(label)


class FakeBank:
    """Подмена транспорта TBankClient: запоминает запросы, отвечает по сценарию."""

    def __init__(self):
        self.inits: list[dict] = []
        self.closing: list[dict] = []
        self.closing_error: Exception | None = None
        self.closing_delay = 0.0
        self.paid: set[str] = set()
        self.orders: dict[str, tuple[str, int]] = {}
        self.counter = 8_000_000_000

    async def init(self, client, **kw):
        self.counter += 1
        pid = str(self.counter)
        self.inits.append(kw)
        self.orders[pid] = (kw["order_id"], kw["amount_kopeks"])
        return ta.TBankInitResult(payment_id=pid, payment_url=f"https://pay.example/{pid}", status="NEW")

    async def get_state(self, client, *, payment_id):
        order_id, amount = self.orders.get(payment_id, (None, None))
        status = "CONFIRMED" if payment_id in self.paid else "NEW"
        return ta.TBankState(payment_id=payment_id, status=status, amount_kopeks=amount, order_id=order_id)

    async def cancel(self, client, **kw):
        return ta.TBankCancelResult(status="CANCELED", original_amount_kopeks=None, new_amount_kopeks=0)

    async def send_closing_receipt(self, client, *, payment_id, receipt):
        if self.closing_delay:
            await asyncio.sleep(self.closing_delay)
        self.closing.append({"payment_id": payment_id, "receipt": receipt})
        if self.closing_error:
            raise self.closing_error


BANK = FakeBank()
ta.TBankClient.init = lambda self, **kw: BANK.init(self, **kw)
ta.TBankClient.get_state = lambda self, **kw: BANK.get_state(self, **kw)
ta.TBankClient.cancel = lambda self, **kw: BANK.cancel(self, **kw)
ta.TBankClient.send_closing_receipt = lambda self, **kw: BANK.send_closing_receipt(self, **kw)


async def seed(n_apps: int) -> dict:
    async with AsyncSessionLocal() as db:
        provider = Provider(code=f"rcpt-{uuid4().hex[:8]}", full_name='ООО "Смоук"', short_name="ООО Смоук")
        db.add(provider)
        await db.flush()
        address = Address(
            provider_id=provider.id, full_address="г. Москва, ул. Чековая, д. 1",
            cadastral_number="77:01:0001001:9", ownership_doc="Свидетельство", ownership_doc_short="Св-во",
            ownership_doc_pages=1, price_6m=Decimal("30000"), price_11m=Decimal("45000"),
            publication_status=AddressPublicationStatus.PUBLISHED.value, is_available=True,
        )
        client = User(email=CLIENT_EMAIL, full_name="Клиент Чеков", role=UserRole.CLIENT.value,
                      email_verified_at=utcnow())
        admin = User(email="smoke-rcpt-admin@example.com", full_name="Админ", role=UserRole.ADMIN.value)
        db.add_all([address, client, admin])
        await db.flush()
        apps = []
        for n in range(n_apps):
            application = Application(
                type="initial_registration", status=ApplicationStatus.AWAITING_PAYMENT.value,
                provider_id=provider.id, address_id=address.id, company_name=f"Чек-{n}",
                planned_client_name=f"Чек-{n}", contact_name="Клиент Чеков", contact_phone="+79001234567",
                contact_email=CLIENT_EMAIL, term_months=11, has_correspondence_service=False,
                created_by=client.id,
            )
            db.add(application)
            apps.append(application)
        await db.flush()
        tokens = {}
        now = utcnow()
        for key, user in (("client", client), ("admin", admin)):
            raw = secrets.token_urlsafe(32)
            db.add(UserSession(user_id=user.id, token_hash=hash_token(raw),
                               expires_at=now + timedelta(hours=2), created_at=now, session_type="web"))
            tokens[key] = raw
        await db.commit()
        return {"apps": [str(a.id) for a in apps], "tokens": tokens}


async def load_payment(payment_id: str) -> Payment:
    async with AsyncSessionLocal() as db:
        return await db.get(Payment, UUID(payment_id))


async def set_payment(payment_id: str, **values) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(Payment).where(Payment.id == UUID(payment_id)).values(**values))
        await db.commit()


async def set_application(application_id: str, status: ApplicationStatus) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(Application).where(Application.id == UUID(application_id)).values(status=status.value)
        )
        await db.commit()


async def admin_events(application_id: str, title: str) -> int:
    async with AsyncSessionLocal() as db:
        return (await db.execute(
            select(func.count()).select_from(ApplicationEvent).where(
                ApplicationEvent.application_id == UUID(application_id),
                ApplicationEvent.audience == "admin", ApplicationEvent.title == title,
            )
        )).scalar_one()


def signed(payment: dict, **fields) -> dict:
    body = {
        "TerminalKey": settings.tbank_terminal_key, "OrderId": payment["id"], "Success": True,
        "Status": "CONFIRMED", "PaymentId": int(payment["provider_payment_id"]), "ErrorCode": "0",
        "Amount": payment["amount_kopeks"],
    }
    body.update(fields)
    body["Token"] = make_token(body, settings.tbank_password)
    return body


async def receipt_is_sql_null(payment_id: str) -> bool:
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        return (await db.execute(
            text("SELECT receipt IS NULL FROM payments WHERE id = :id"), {"id": payment_id}
        )).scalar_one()


async def run_checks() -> None:
    ids = await seed(6)
    apps, tokens = ids["apps"], ids["tokens"]
    csrf = secrets.token_urlsafe(16)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://smoke", headers={CSRF_HEADER_NAME: csrf}
    ) as http:

        def login_as(who: str) -> None:
            http.cookies.clear()
            http.cookies.set(settings.session_cookie_name, tokens[who])
            http.cookies.set(CSRF_COOKIE_NAME, csrf)

        async def pay(application_id: str) -> dict:
            login_as("client")
            r = await http.post("/api/v1/payments/initiate", json={"application_id": application_id})
            assert r.status_code == 201, r.text
            payment = r.json()
            BANK.paid.add(payment["provider_payment_id"])
            http.cookies.clear()
            r = await http.post(NOTIFY, content=json.dumps(signed(payment)), headers=JSON)
            assert r.text == "OK", r.text
            return payment

        async def approve(application_id: str):
            await set_application(application_id, ApplicationStatus.DOCUMENTS_REVIEW)
            login_as("admin")
            return await http.post(f"/api/v1/workflow/applications/{application_id}/actions/approve_documents")

        print("\n== чек предоплаты уходит в Init и сохраняется снимком ==")
        pay0 = await pay(apps[0])
        sent = BANK.inits[-1]["receipt"]
        check(sent is not None and sent["Taxation"] == "osn", "Receipt в Init, СНО osn")
        check(sent["Email"] == CLIENT_EMAIL, "чек — на почту заявителя")
        check(sent["Items"][0]["Tax"] == "vat122" and sent["Items"][0]["PaymentMethod"] == "full_prepayment",
              "предоплата 100%, НДС 22/122")
        stored = await load_payment(pay0["id"])
        check(stored.receipt == sent, "снимок чека в JSONB совпадает с отправленным")
        check(stored.status == PaymentStatus.SUCCEEDED.value, f"платёж оплачен ({stored.status})")
        check(stored.closing_receipt_status is None, "закрывающий чек пока не нужен")

        print("\n== выдача документов → закрывающий чек сразу после коммита ==")
        r = await approve(apps[0])
        check(r.status_code == 200 and r.json()["status"] == "ready_for_client", f"документы выданы ({r.status_code})")
        stored = await load_payment(pay0["id"])
        check(stored.closing_receipt_status == "sent", f"закрывающий чек отправлен ({stored.closing_receipt_status})")
        check(len(BANK.closing) == 1, f"ровно один запрос в банк ({len(BANK.closing)})")
        closing = BANK.closing[0]["receipt"]
        check(closing["Items"][0]["PaymentMethod"] == "full_payment" and closing["Items"][0]["Tax"] == "vat22",
              "полный расчёт, НДС 22%")
        check(closing["Payments"] == {"Electronic": 0, "AdvancePayment": pay0["amount_kopeks"]}, "зачёт аванса")
        check(BANK.closing[0]["payment_id"] == pay0["provider_payment_id"], "по PaymentId банка")
        await tbank_receipts.send_due_for_application(UUID(apps[0]))
        check(len(BANK.closing) == 1, "повторный запуск не шлёт второй чек")

        print("\n== спор и возврат в «Готово» не дублируют чек ==")
        await set_application(apps[0], ApplicationStatus.DISPUTE)
        login_as("admin")
        r = await http.post(f"/api/v1/workflow/applications/{apps[0]}/actions/resolve_dispute")
        check(r.status_code == 200, f"спор закрыт ({r.status_code})")
        check(len(BANK.closing) == 1, "второго закрывающего чека нет")

        print("\n== пять одновременных отправок → один чек (захват строки) ==")
        pay1 = await pay(apps[1])
        await set_payment(pay1["id"], closing_receipt_status="due")
        BANK.closing_delay = 0.3
        before = len(BANK.closing)

        async def one():
            async with AsyncSessionLocal() as db:
                return await tbank_receipts.send_closing_receipt(db, UUID(pay1["id"]))

        results = await asyncio.gather(*[one() for _ in range(5)])
        BANK.closing_delay = 0
        check(len(BANK.closing) - before == 1, f"в банк ушёл один чек ({len(BANK.closing) - before})")
        check(sorted(map(str, results)) == ["None"] * 4 + ["sent"], f"итоги {results}")

        print("\n== обрыв связи → unknown, без автоповтора, алерт ==")
        pay2 = await pay(apps[2])
        BANK.closing_error = ta.TBankError("Т-Банк недоступен (SendClosingReceipt): ReadTimeout")
        r = await approve(apps[2])
        BANK.closing_error = None
        stored = await load_payment(pay2["id"])
        check(stored.closing_receipt_status == "unknown", f"статус unknown ({stored.closing_receipt_status})")
        check(await admin_events(apps[2], "Проверьте закрывающий чек") == 1, "админ предупреждён")
        from scripts.reconcile_tbank_payments import _run as reconcile

        count = len(BANK.closing)
        await reconcile(limit=50)
        check(len(BANK.closing) == count, "крон unknown вслепую не повторяет")

        print("\n== админ: «чек найден в ЛК» ==")
        login_as("admin")
        r = await http.post(f"/api/v1/payments/{pay2['id']}/closing-receipt", json={"action": "mark_sent"})
        check(r.status_code == 200 and r.json()["closing_receipt_status"] == "sent", f"отмечен ({r.status_code})")

        print("\n== отказ банка → повторы кроном до лимита, алерт один раз ==")
        pay3 = await pay(apps[3])
        BANK.closing_error = ta.TBankError("Касса недоступна", error_code="1051")
        await approve(apps[3])
        for _ in range(settings.tbank_closing_receipt_max_attempts + 2):
            await reconcile(limit=50)
        stored = await load_payment(pay3["id"])
        check(stored.closing_receipt_status == "failed", f"failed ({stored.closing_receipt_status})")
        check(stored.closing_receipt_attempts == settings.tbank_closing_receipt_max_attempts,
              f"попыток ровно {settings.tbank_closing_receipt_max_attempts} ({stored.closing_receipt_attempts})")
        check(await admin_events(apps[3], "Закрывающий чек не отправлен") == 1, "алерт один раз")

        print("\n== админ исправил кассу и отправил повторно ==")
        BANK.closing_error = None
        login_as("admin")
        r = await http.post(f"/api/v1/payments/{pay3['id']}/closing-receipt", json={"action": "send"})
        check(r.status_code == 200 and r.json()["closing_receipt_status"] == "sent", f"отправлен ({r.status_code} {r.text[:120]})")

        print("\n== зависшая отправка (процесс упал) → unknown ==")
        await set_payment(pay3["id"], closing_receipt_status="sending",
                          closing_receipt_at=utcnow() - timedelta(minutes=30))
        await reconcile(limit=50)
        stored = await load_payment(pay3["id"])
        check(stored.closing_receipt_status == "unknown", f"unknown ({stored.closing_receipt_status})")

        print("\n== чеки выключены: receipt — SQL NULL, закрывающий не заводится (ревизия) ==")
        settings.tbank_receipts_enabled = False
        try:
            pay4 = await pay(apps[4])
        finally:
            settings.tbank_receipts_enabled = True
        check(BANK.inits[-1]["receipt"] is None, "Init без Receipt")
        check(await receipt_is_sql_null(pay4["id"]), "в базе SQL NULL, а не JSON null")
        count = len(BANK.closing)
        r = await approve(apps[4])
        check(r.status_code == 200, f"документы выданы ({r.status_code})")
        stored = await load_payment(pay4["id"])
        check(stored.closing_receipt_status is None, f"закрывающий не заведён ({stored.closing_receipt_status})")
        check(len(BANK.closing) == count, "в банк ничего не ушло")

        print("\n== запрос точно не ушёл (нет соединения) → в очередь, крон досылает ==")
        pay5 = await pay(apps[5])
        BANK.closing_error = ta.TBankError("Т-Банк недоступен: ConnectError", not_sent=True)
        await approve(apps[5])
        stored = await load_payment(pay5["id"])
        check(stored.closing_receipt_status == "due", f"вернулся в очередь ({stored.closing_receipt_status})")
        check(stored.closing_receipt_attempts == 0, f"попытка не засчитана ({stored.closing_receipt_attempts})")
        check(await admin_events(apps[5], "Проверьте закрывающий чек") == 0, "без ложного алерта")
        BANK.closing_error = None
        await reconcile(limit=50)
        stored = await load_payment(pay5["id"])
        check(stored.closing_receipt_status == "sent", f"крон дослал ({stored.closing_receipt_status})")

        print("\n== касса не пробила чек → алерт по уведомлению RECEIPT ==")
        http.cookies.clear()
        body = signed(pay1, Status="RECEIPT", Success=False, ErrorCode="1051", Message="Касса недоступна")
        r = await http.post(NOTIFY, content=json.dumps(body), headers=JSON)
        check(r.text == "OK", "банку ответили OK")
        check(await admin_events(apps[1], "Касса не пробила чек") == 1, "админ предупреждён")
        await http.post(NOTIFY, content=json.dumps(body), headers=JSON)
        check(await admin_events(apps[1], "Касса не пробила чек") == 1, "повтор уведомления не дублирует алерт")


async def main() -> int:
    if "tbank_smoke" not in settings.database_url:
        print("Отказ: только база tbank_smoke.")
        return 2
    if not settings.tbank_receipts_enabled or settings.payment_provider != "tbank":
        print("Отказ: нужны PAYMENT_PROVIDER=tbank и TBANK_RECEIPTS_ENABLED=true.")
        return 2
    await run_checks()
    print("\n" + ("ВСЁ ЗЕЛЁНОЕ" if not FAILURES else f"ПРОВАЛЫ: {FAILURES}"))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
