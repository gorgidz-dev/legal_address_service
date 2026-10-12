"""Смоук статус-трекера (этап 6): расписка ИФНС, дата регистрации, напоминания,
подтверждение регистрации без выплаты — на настоящем Postgres и HTTP-стеке.

Юнит-тесты не видят SQL и файлового хранилища; здесь — миграции 0037–0038,
загрузка файла multipart и предпросмотр разбора, расписка у собственника,
идемпотентность напоминаний по payload (JSONB has_key), сверка первичной
регистрации по названию и адресу и смены адреса по ИНН и адресу (с
подтверждением без выплаты при счёте собственника).

Подменены: DaData (два известных юрлица) и чтение текста из PDF — собрать
настоящий PDF с кириллицей здесь нечем, а образец расписки с персональными
данными в публичный репозиторий не кладём. Разбор текста бланка проверяет
tests/test_ifns_receipt.py на обезличенной копии настоящего бланка ФНС.

Запуск — только на отдельной пустой базе с tracker_smoke в имени:
    docker exec uradres-pg createdb -U postgres tracker_smoke
    DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/tracker_smoke \\
        .venv/bin/alembic upgrade head
    DATABASE_URL=...tracker_smoke PYTHONPATH=. .venv/bin/python -X utf8 -m scripts.smoke_registration_tracker
После — dropdb.
"""
from __future__ import annotations

import asyncio
import importlib.util
import secrets
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
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
from app.models.client import Client
from app.models.owner_payout import OwnerPayout
from app.models.payment import Payment
from app.models.provider import Provider
from app.models.user import User
from app.models.user_session import UserSession
from app.routers import owner_payouts as payouts_router
from app.services.auth_security import hash_token
from app.services.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.schemas.client import DaDataLookupResponse
from app.services import application_documents
from app.services.ifns_receipt import parse_receipt_text
from app.services.registration_reminders import send_registration_check_reminders
from scripts.smoke_owner_payouts import ADDRESS, EGRUL_SAME, INN_ELSEWHERE, INN_OK

def _fns_blank() -> str:
    """Обезличенный бланк расписки из tests/test_ifns_receipt.py (tests — не пакет)."""
    path = Path(__file__).resolve().parents[1] / "tests" / "test_ifns_receipt.py"
    spec = importlib.util.spec_from_file_location("ifns_receipt_blank", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FNS_BLANK


FNS_BLANK = _fns_blank()
FAILURES: list[str] = []
MSK = timezone(timedelta(hours=3))
NEW_NAME = 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРИМЕР"'
MOVING_OGRN = "1027700229193"  # ОГРН компании с INN_ELSEWHERE (публичные данные)


def receipt_pdf(**changes: str) -> bytes:
    """«PDF» расписки: обезличенный текст бланка ФНС, на который подменён разбор."""
    text = FNS_BLANK
    for old, new in changes.items():
        text = text.replace(old, new)
    return b"%PDF-smoke\n" + text.encode("utf-8")


def fake_parse(content: bytes):
    """Вместо pypdf: «текст» из нашего «PDF»; без маркера — PDF без текста (скан)."""
    if not content.startswith(b"%PDF-smoke\n"):
        return parse_receipt_text("")
    return parse_receipt_text(content[len(b"%PDF-smoke\n"):].decode("utf-8"))


class TrackerDaData:
    """ЕГРЮЛ: новая компания «ПРИМЕР» (первичка) и «Переезжающая» (смена адреса),
    обе уже зарегистрированы по адресу заявки."""

    def __init__(self, registered_on: date):
        self.registered_on = registered_on

    def invalidate(self, inn: str) -> None:
        pass

    async def lookup(self, inn: str):
        known = {
            INN_OK: (NEW_NAME, "1027700132195"),
            INN_ELSEWHERE: ('ООО "Переезжающая"', MOVING_OGRN),
        }
        if inn not in known:
            return None
        name, ogrn = known[inn]
        return DaDataLookupResponse(
            inn=inn, kpp="770101001", ogrn=ogrn, full_name=name, short_name=name, legal_address=EGRUL_SAME,
            kladr_id=None, signatory_name=None, signatory_position=None, okved_main_code=None,
            okved_main_name=None, egrul_status="ACTIVE",
            blockers=DaDataLookupResponse.Blockers(
                liquidating_or_liquidated=False, bankrupt=False, signatory_disqualified=False, is_branch=False,
            ),
            registration_date=self.registered_on,
        )

    async def search_by_name(self, name: str):
        return [await self.lookup(INN_ELSEWHERE), await self.lookup(INN_OK)]


def check(condition: bool, label: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}")
    if not condition:
        FAILURES.append(label)


async def seed() -> dict:
    now = utcnow()
    async with AsyncSessionLocal() as db:
        provider = Provider(code=f"smoke-trk-{uuid4().hex[:6]}", full_name='ООО "Собственник"',
                            short_name="ООО Собственник", commission_percent=Decimal("19"))
        db.add(provider)
        await db.flush()
        address = Address(
            provider_id=provider.id, full_address=ADDRESS, cadastral_number=f"77:01:{uuid4().int % 10**7}:2",
            ownership_doc="Свидетельство", ownership_doc_short="Св-во", ownership_doc_pages=1,
            price_6m=Decimal("18000"), price_11m=Decimal("30000"),
            publication_status=AddressPublicationStatus.PUBLISHED.value, is_available=True,
        )
        company = Client(inn=INN_ELSEWHERE, ogrn=MOVING_OGRN, full_name='ООО "Переезжающая"',
                         short_name='ООО "Переезжающая"')
        users = {
            "admin": User(email="smoke-trk-admin@example.com", full_name="Админ", role=UserRole.ADMIN.value),
            "client": User(email="smoke-trk-client@example.com", full_name="Клиент", role=UserRole.CLIENT.value),
            "owner": User(email="smoke-trk-owner@example.com", full_name="Собственник", role=UserRole.OWNER.value,
                          provider_id=provider.id),
        }
        db.add_all([address, company, *users.values()])
        await db.flush()

        def application(kind: str, status: ApplicationStatus) -> Application:
            values = dict(
                type=kind, status=status.value, provider_id=provider.id, address_id=address.id,
                contact_name="Клиент", contact_phone="+79001234567", contact_email=users["client"].email,
                term_months=11, has_correspondence_service=False, created_by=users["client"].id,
            )
            if kind == "initial_registration":
                # В заявке название без формы — в расписке и ЕГРЮЛ полное.
                values.update(company_name="ООО «Пример»", planned_client_name="ООО «Пример»")
            else:
                values.update(client_id=company.id, company_name='ООО "Переезжающая"', notice_period="1m")
            return Application(**values)

        first = application("initial_registration", ApplicationStatus.DOCUMENTS_PREPARING)
        moving = application("address_change", ApplicationStatus.READY_FOR_CLIENT)
        db.add_all([first, moving])
        await db.flush()
        # Смена адреса оплачена по счёту собственника — денег у площадки нет.
        db.add(Payment(
            application_id=moving.id, provider="manual_invoice", payer_type="juridical",
            status=PaymentStatus.SUCCEEDED.value, amount_kopeks=3_000_000, currency="RUR",
            pay_for="application", initiated_by=users["client"].id,
        ))
        tokens = {}
        for key, user in users.items():
            raw = secrets.token_urlsafe(32)
            db.add(UserSession(user_id=user.id, token_hash=hash_token(raw), expires_at=now + timedelta(hours=2),
                               created_at=now, session_type="web"))
            tokens[key] = raw
        await db.commit()
        return {"first": str(first.id), "moving": str(moving.id), "tokens": tokens}


async def set_status(application_id: str, status: ApplicationStatus) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(update(Application).where(Application.id == UUID(application_id)).values(status=status.value))
        await db.commit()


async def load(application_id: str) -> Application:
    async with AsyncSessionLocal() as db:
        return await db.get(Application, UUID(application_id))


async def reminders(at: datetime) -> list[tuple[str, str]]:
    async with AsyncSessionLocal() as db:
        events = await send_registration_check_reminders(db=db, now=at)
        await db.commit()
        return [(e.audience, e.title) for e in events]


async def run_checks() -> None:
    ids = await seed()
    first, moving, tokens = ids["first"], ids["moving"], ids["tokens"]
    payouts_router.get_dadata_service = lambda: TrackerDaData(date.today())  # type: ignore[assignment]
    application_documents.parse_receipt_pdf = fake_parse  # type: ignore[assignment]
    csrf = secrets.token_urlsafe(16)
    today = utcnow().astimezone(MSK).date()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://smoke", headers={CSRF_HEADER_NAME: csrf}
    ) as http:

        def login_as(who: str) -> None:
            http.cookies.clear()
            http.cookies.set(settings.session_cookie_name, tokens[who])
            http.cookies.set(CSRF_COOKIE_NAME, csrf)

        async def upload(application_id: str, *, name="receipt.pdf", content=None, when: date | None = None):
            content = receipt_pdf() if content is None else content
            return await http.post(
                f"/api/v1/workflow/applications/{application_id}/ifns-receipt",
                files={"file": (name, content, "application/pdf")},
                data={"expected_registration_on": (when or today + timedelta(days=3)).isoformat()},
            )

        print("\n== клиент загружает расписку ==")
        login_as("client")
        r = await upload(first)
        check(r.status_code == 409, f"до выдачи документов — 409 ({r.status_code})")
        await set_status(first, ApplicationStatus.READY_FOR_CLIENT)
        r = await upload(first, name="receipt.exe")
        check(r.status_code == 422, f"не PDF — 422 ({r.status_code})")
        r = await upload(first, content=b"")
        check(r.status_code == 422, f"пустой файл — 422 ({r.status_code})")
        r = await upload(first, content=b"%PDF-1.4 scanned image")
        check(r.status_code == 422 and "скан" in r.text, f"PDF без текста (скан) — 422 ({r.status_code})")
        r = await http.post(f"/api/v1/workflow/applications/{first}/ifns-receipt/preview",
                            files={"file": ("receipt.pdf", receipt_pdf(), "application/pdf")})
        body = r.json()
        check(r.status_code == 200 and body["expected_on"] == "2026-05-08" and body["company_name"] == NEW_NAME,
              f"предпросмотр: дата и название из расписки ({r.status_code} {r.text[:120]})")
        r = await upload(first, when=today + timedelta(days=60))
        check(r.status_code == 422, f"дата через 2 месяца — 422 ({r.status_code})")
        r = await upload(first)
        check(r.status_code == 201 and r.json()["registration_expected_on"] == (today + timedelta(days=3)).isoformat(),
              f"расписка принята ({r.status_code} {r.text[:120]})")
        receipt_id = r.json()["document"]["id"] if r.status_code == 201 else None
        check(r.status_code == 201 and r.json()["receipt"]["number"] == "100000А", "разбор сохранён вместе с распиской")
        application = await load(first)
        check(application.ifns_receipt_uploaded_at is not None, "время загрузки записано в заявку")
        login_as("owner")
        r = await upload(first)
        check(r.status_code == 404, f"собственник расписку не загружает ({r.status_code})")

        print("\n== кто видит расписку ==")
        r = await http.get(f"/api/v1/workflow/applications/{first}/documents")
        check(r.status_code == 200 and any(d["kind"] == "ifns_receipt" for d in r.json()), "собственник видит расписку в документах")
        r = await http.get(f"/api/v1/workflow/applications/{first}/documents/{receipt_id}/download")
        check(r.status_code == 200 and r.content == receipt_pdf(), f"собственник скачивает расписку ({r.status_code})")
        r = await http.get("/api/v1/owner/dashboard")
        row = next((a for a in r.json()["applications"] if a["id"] == first), None)
        check(row is not None and row["registration_expected_on"] == (today + timedelta(days=3)).isoformat(),
              "собственник видит дату ожидаемой регистрации")
        check(row is not None and (row.get("ifns_receipt") or {}).get("ifns", "").startswith("Межрайонная"),
              "собственник видит инспекцию из расписки")
        login_as("client")
        r = await http.get(f"/api/v1/workflow/applications/{first}/documents/{receipt_id}/download")
        check(r.status_code == 200 and r.content == receipt_pdf(), f"клиент скачивает свою расписку ({r.status_code})")
        r = await http.get("/api/v1/client/applications")
        row = next((a for a in r.json() if a["id"] == first), None)
        check(row is not None and row["ifns_receipt_uploaded_at"], "в кабинете клиента трекер видит расписку")
        login_as("admin")
        r = await http.get(f"/api/v1/workflow/applications/{first}/documents")
        check(any(d["kind"] == "ifns_receipt" for d in r.json()), "админ видит расписку")

        print("\n== напоминания по дате из расписки ==")
        before = datetime.combine(today + timedelta(days=2), datetime.min.time(), MSK) + timedelta(hours=9)
        check(await reminders(before) == [], "до даты регистрации — тихо")
        on_date = datetime.combine(today + timedelta(days=3), datetime.min.time(), MSK) + timedelta(hours=9)
        sent = await reminders(on_date)
        check(sent == [("admin", "Пора сверить регистрацию")], f"в день регистрации — админу «пора сверить» ({sent})")
        check(await reminders(on_date + timedelta(days=1)) == [], "на следующий день повторов нет")
        login_as("client")
        r = await upload(first, when=today + timedelta(days=5))
        check(r.status_code == 201, f"новая расписка с другой датой ({r.status_code})")
        later = datetime.combine(today + timedelta(days=5), datetime.min.time(), MSK) + timedelta(hours=9)
        check(len(await reminders(later)) == 1, "по новой дате напоминание идёт заново")

        print("\n== смена адреса по счёту собственника: ИНН + адрес, без выплаты ==")
        login_as("client")
        r = await upload(moving, content=receipt_pdf(**{"1027700132195": "1037700000006"}))
        check(r.status_code == 422 and "другая компания" in r.text, f"расписка чужой компании (ОГРН) — 422 ({r.status_code})")
        r = await upload(moving, content=receipt_pdf(**{"1027700132195": MOVING_OGRN}))
        check(r.status_code == 201, f"расписка своей компании принята ({r.status_code})")
        login_as("admin")
        r = await http.post(f"/api/v1/payouts/applications/{moving}/registration/check", json={})
        body = r.json()
        check(r.status_code == 200 and body["mode"] == "inn" and body["expected_inn"] == INN_ELSEWHERE,
              f"смена адреса сверяется по ИНН из заявки ({r.status_code})")
        check(body.get("candidates") and body["candidates"][0]["address_matches"] is True, "адрес в ЕГРЮЛ уже новый")
        r = await http.post(f"/api/v1/payouts/applications/{moving}/registration/confirm", json={"inn": INN_OK})
        check(r.status_code == 409 and "меняет адрес компания" in r.text, f"чужой ИНН не подтвердить ({r.status_code})")
        r = await http.post(f"/api/v1/payouts/applications/{moving}/registration/confirm", json={})
        body = r.json()
        check(r.status_code == 200 and body["payout"] is None and body["registration_confirmed_at"],
              f"подтверждено без выплаты ({r.status_code} {r.text[:150]})")
        async with AsyncSessionLocal() as db:
            n = (await db.execute(select(func.count(OwnerPayout.id)).where(OwnerPayout.application_id == UUID(moving)))).scalar_one()
        check(n == 0, "выплата не заведена")
        login_as("client")
        r = await upload(moving)
        check(r.status_code == 409, f"после подтверждения расписка не нужна ({r.status_code})")
        r = await http.get("/api/v1/client/applications")
        row = next((a for a in r.json() if a["id"] == moving), None)
        check(row is not None and row["registration_confirmed_at"], "клиент видит подтверждённую регистрацию")

        print("\n== первичка: название + адрес ==")
        login_as("admin")
        r = await http.post(f"/api/v1/payouts/applications/{first}/registration/check", json={})
        body = r.json()
        check(r.status_code == 200 and body["mode"] == "name" and body["query"] == NEW_NAME,
              f"поиск по названию из расписки ({r.status_code} {r.text[:120]})")
        top = (body.get("candidates") or [{}])[0]
        check(top.get("inn") == INN_OK and top.get("name_matches") is True and top.get("address_matches") is True,
              "первым — кандидат с совпавшими названием и адресом")
        r = await http.post(f"/api/v1/payouts/applications/{first}/registration/confirm", json={"inn": INN_ELSEWHERE})
        check(r.status_code == 409, f"кандидат с чужим названием без ручной отметки — 409 ({r.status_code})")
        r = await http.post(f"/api/v1/payouts/applications/{first}/registration/confirm", json={"inn": INN_OK})
        check(r.status_code == 200 and r.json()["payout"] is None, f"денег через площадку не было — без выплаты ({r.status_code})")
        far = datetime.combine(today + timedelta(days=10), datetime.min.time(), MSK)
        check(await reminders(far) == [], "подтверждённые заявки напоминаний не получают")
        async with AsyncSessionLocal() as db:
            client_events = (await db.execute(
                select(ApplicationEvent.payload).where(
                    ApplicationEvent.application_id == UUID(first), ApplicationEvent.audience == "client",
                    ApplicationEvent.title == "Регистрация подтверждена",
                )
            )).scalars().all()
        check(client_events and all("payout_id" not in (p or {}) for p in client_events),
              "в событии клиента нет внутренних полей выплаты")


async def main() -> int:
    if "tracker_smoke" not in settings.database_url:
        print("Отказ: скрипт пишет данные и запускается только на базе tracker_smoke.")
        return 2
    await run_checks()
    print("\n" + ("ВСЁ ЗЕЛЁНОЕ" if not FAILURES else f"ПРОВАЛЫ: {FAILURES}"))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
