"""Чеки 54-ФЗ по оплатам Т-Банка: предоплата в Init, полный расчёт при выдаче документов.

Главный риск — второй закрывающий чек: у SendClosingReceipt нет ключа
идемпотентности, поэтому при неясном исходе чек не повторяется вслепую.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.enums import NotificationAudience, PaymentProvider, PaymentStatus
from app.models.application import Application
from app.models.application_event import ApplicationEvent
from app.models.payment import Payment
from app.models.provider import Provider
from app.services import tbank_receipts
from app.services.tbank_acquiring import TBankError
from app.services.tbank_receipts import (
    DUE,
    FAILED,
    SENT,
    UNKNOWN,
    ReceiptContactMissing,
    build_closing_receipt,
    build_prepayment_receipt,
    mark_closing_receipt_due,
    send_closing_receipt,
)

AMOUNT = 3_000_000
TERMINAL = "1000000000001"


def _now():
    return datetime.now(timezone.utc)


# ============================================================
# Сборка чеков
# ============================================================

#: Собственник адреса — поставщик в агентском чеке.
SUPPLIER = tbank_receipts.Supplier(
    name="Индивидуальный предприниматель Иванов Иван Иванович",
    inn="500100732259",
    phone="+79161234567",
    vat="none",
)


def _prepayment(**kw):
    return build_prepayment_receipt(
        amount_kopeks=kw.pop("amount_kopeks", AMOUNT),
        email=kw.pop("email", "a@b.ru"),
        phone=kw.pop("phone", None),
        supplier=kw.pop("supplier", SUPPLIER),
    )


def test_agent_receipt_sells_owners_service_with_owners_vat() -> None:
    """Агентская схема (решение владельца 18.10.2026): позиция — услуга собственника."""
    receipt = _prepayment(email="client@example.ru")
    assert receipt["Taxation"] == "osn"  # СНО — пользователя кассы, то есть ООО
    assert receipt["Email"] == "client@example.ru"
    assert receipt["FfdVersion"] == "1.2"
    [item] = receipt["Items"]
    assert item == {
        "Name": "Предоставление юридического адреса",
        "Price": AMOUNT,
        "Quantity": 1,
        "Amount": AMOUNT,
        "Tax": "none",  # собственник без НДС — НДС ООО к позиции отношения не имеет
        "PaymentMethod": "full_prepayment",
        "PaymentObject": "service",
        "MeasurementUnit": "шт",
        "AgentData": {"AgentSign": "another"},
        "SupplierInfo": {
            "Phones": ["+79161234567"],
            "Name": "Индивидуальный предприниматель Иванов Иван Иванович",
            "Inn": "500100732259",
        },
    }


@pytest.mark.parametrize(("vat", "prepaid", "full"), [("vat22", "vat122", "vat22"), ("vat5", "vat105", "vat5"), ("none", "none", "none")])
def test_owner_vat_payer_gets_calculated_rate_then_full_rate(vat, prepaid, full) -> None:
    prepayment = _prepayment(supplier=tbank_receipts.Supplier("ООО «Адрес»", "7707083893", "+79161234567", vat))
    assert prepayment["Items"][0]["Tax"] == prepaid
    closing = build_closing_receipt(prepayment)
    [item] = closing["Items"]
    assert item["Tax"] == full
    # Поставщик и признак агента — те же, что в чеке предоплаты.
    assert item["AgentData"] == prepayment["Items"][0]["AgentData"]
    assert item["SupplierInfo"] == prepayment["Items"][0]["SupplierInfo"]


def test_long_supplier_name_leaves_room_for_phone() -> None:
    receipt = _prepayment(supplier=tbank_receipts.Supplier("Я" * 300, "500100732259", "+79161234567", "none"))
    info = receipt["Items"][0]["SupplierInfo"]
    # Тег 1225: наименование + (телефон + 4) на каждый — не больше 239.
    assert len(info["Name"]) + len(info["Phones"][0]) + 4 == 239


def test_agent_receipt_without_supplier_is_refused() -> None:
    with pytest.raises(tbank_receipts.SupplierDataMissing):
        build_prepayment_receipt(amount_kopeks=AMOUNT, email="a@b.ru", phone=None)


def _provider(**kw):
    values = dict(
        full_name="ИП Иванов Иван Иванович", inn="500100732259", phone="8 (916) 123-45-67", receipt_vat="none",
    )
    values.update(kw)
    return SimpleNamespace(**values)


def test_supplier_is_taken_from_owner_card() -> None:
    supplier = tbank_receipts.supplier_from_provider(_provider())
    assert supplier == tbank_receipts.Supplier("ИП Иванов Иван Иванович", "500100732259", "+79161234567", "none")


def test_missing_owner_data_is_listed_not_guessed() -> None:
    with pytest.raises(tbank_receipts.SupplierDataMissing) as caught:
        tbank_receipts.supplier_from_provider(_provider(inn=None, phone="12", receipt_vat=None, full_name=" "))
    # Ставку НДС не подставляем «без НДС» молча: ошибка в чеке — штраф.
    assert caught.value.missing == ["полное наименование", "ИНН", "телефон", "ставка НДС"]
    with pytest.raises(tbank_receipts.SupplierDataMissing):
        tbank_receipts.supplier_from_provider(None)


def test_own_service_receipt_when_agent_scheme_is_off(monkeypatch) -> None:
    """Прежняя схема (признак агента пуст): вся сумма — услуга ООО с НДС ООО."""
    monkeypatch.setattr(tbank_receipts.settings, "tbank_receipt_agent_sign", "")
    receipt = build_prepayment_receipt(amount_kopeks=AMOUNT, email="client@example.ru", phone=None)
    [item] = receipt["Items"]
    assert item == {
        "Name": "Услуги по подбору юридического адреса и подготовке документов",
        "Price": AMOUNT,
        "Quantity": 1,
        "Amount": AMOUNT,
        "Tax": "vat122",  # расчётная ставка в чеке предоплаты (письмо АБ-4-20/11248@)
        "PaymentMethod": "full_prepayment",
        "PaymentObject": "service",
        "MeasurementUnit": "шт",
    }
    assert build_closing_receipt(receipt)["Items"][0]["Tax"] == "vat22"


def test_link_receipt_is_current_only_with_same_owner_data(monkeypatch) -> None:
    receipt = _prepayment()
    assert tbank_receipts.receipt_is_current(receipt, SUPPLIER)
    for changed in (
        tbank_receipts.Supplier(SUPPLIER.name, SUPPLIER.inn, SUPPLIER.phone, "vat22"),  # исправили НДС
        tbank_receipts.Supplier(SUPPLIER.name, "7707083893", SUPPLIER.phone, "none"),  # исправили ИНН
    ):
        assert not tbank_receipts.receipt_is_current(receipt, changed)
    assert not tbank_receipts.receipt_is_current(receipt, None)
    # Схему выключили: агентский чек в ссылке устарел, а чек ООО — нет.
    monkeypatch.setattr(tbank_receipts.settings, "tbank_receipt_agent_sign", "")
    assert not tbank_receipts.receipt_is_current(receipt, None)
    own = build_prepayment_receipt(amount_kopeks=AMOUNT, email="a@b.ru", phone=None)
    assert tbank_receipts.receipt_is_current(own, None)
    # И обратно: чек ООО при включённой агентской схеме устарел.
    monkeypatch.setattr(tbank_receipts.settings, "tbank_receipt_agent_sign", "another")
    assert not tbank_receipts.receipt_is_current(own, SUPPLIER)


def test_receipt_amount_equals_payment_amount() -> None:
    # Требование Init: сумма позиций чека = Amount платежа, иначе банк откажет.
    receipt = _prepayment(amount_kopeks=1_234_567)
    assert sum(item["Amount"] for item in receipt["Items"]) == 1_234_567


@pytest.mark.parametrize(
    ("phone", "expected"),
    [("+7 925 747-11-03", "+79257471103"), ("89257471103", "+79257471103"), ("9257471103", "+79257471103")],
)
def test_phone_is_used_when_email_is_missing(phone, expected) -> None:
    receipt = _prepayment(email=None, phone=phone)
    assert receipt["Phone"] == expected
    assert "Email" not in receipt


def test_no_contact_means_no_receipt() -> None:
    with pytest.raises(ReceiptContactMissing):
        _prepayment(email="", phone="12")


def test_settings_drive_rate_and_ffd(monkeypatch) -> None:
    monkeypatch.setattr(tbank_receipts.settings, "tbank_receipt_agent_sign", "")
    monkeypatch.setattr(tbank_receipts.settings, "tbank_receipt_vat", "none")
    monkeypatch.setattr(tbank_receipts.settings, "tbank_receipt_ffd_version", "")
    monkeypatch.setattr(tbank_receipts.settings, "tbank_receipt_item_name", "Я" * 200)
    receipt = build_prepayment_receipt(amount_kopeks=AMOUNT, email="a@b.ru", phone=None)
    assert receipt["Items"][0]["Tax"] == "none"
    assert "FfdVersion" not in receipt  # пусто — не передаём
    assert len(receipt["Items"][0]["Name"]) == 128


def test_closing_receipt_is_full_payment_by_advance() -> None:
    prepayment = _prepayment()
    closing = build_closing_receipt(prepayment)
    [item] = closing["Items"]
    assert item["PaymentMethod"] == "full_payment"
    assert item["Amount"] == AMOUNT and item["Name"] == prepayment["Items"][0]["Name"]
    assert closing["Email"] == "a@b.ru"
    # Новых денег нет — зачёт аванса (тег 1215); сумма видов оплаты = сумме позиций.
    assert closing["Payments"] == {"Electronic": 0, "AdvancePayment": AMOUNT}
    # Снимок предоплаты не испорчен (из него же строится повтор).
    assert prepayment["Items"][0]["PaymentMethod"] == "full_prepayment"


# ============================================================
# Постановка в очередь при выдаче документов
# ============================================================


def _payment(**kw) -> Payment:
    p = Payment(
        application_id=kw.pop("application_id", uuid4()),
        provider=PaymentProvider.TBANK.value,
        payer_type="individual",
        status=kw.pop("status", PaymentStatus.SUCCEEDED.value),
        amount_kopeks=AMOUNT,
        currency="RUR",
        pay_for="Юр. адрес",
        provider_payment_id=kw.pop("provider_payment_id", "9287980194"),
        provider_account=kw.pop("provider_account", TERMINAL),
        receipt=kw.pop("receipt", _prepayment()),
        closing_receipt_attempts=kw.pop("closing_receipt_attempts", 1),
        **kw,
    )
    p.id = uuid4()
    p.created_at = _now()
    return p


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._rows))

    def scalar_one(self):
        return self._rows[0]


class _FakeDB:
    def __init__(self, rows=(), *, owner_vat="none"):
        self.rows = list(rows)
        self.added: list = []
        self.commits = 0
        # Заявка и собственник для сверки НДС при постановке закрывающего чека.
        self.provider = SimpleNamespace(id=uuid4(), receipt_vat=owner_vat)

    async def get(self, model, key):
        if model is Application:
            return SimpleNamespace(id=key, provider_id=self.provider.id)
        if model is Provider and key == self.provider.id:
            return self.provider
        return None

    async def execute(self, stmt):
        if hasattr(stmt, "column_descriptions") and stmt.column_descriptions[0].get("entity") is Payment:
            return _Rows(self.rows)
        raise RuntimeError("no subscriptions in unit tests")  # dispatch_event

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        for item in self.added:
            if getattr(item, "id", None) is None:
                item.id = uuid4()

    async def commit(self):
        self.commits += 1

    def admin_titles(self) -> list[str]:
        return [
            e.title for e in self.added
            if isinstance(e, ApplicationEvent) and e.audience == NotificationAudience.ADMIN.value
        ]


@pytest.mark.asyncio
async def test_documents_ready_queues_closing_receipt() -> None:
    payment = _payment()
    db = _FakeDB([payment])
    assert await mark_closing_receipt_due(db, payment.application_id) is payment
    assert payment.closing_receipt_status == DUE


@pytest.mark.asyncio
async def test_owner_vat_changed_after_payment_warns_admin() -> None:
    payment = _payment()  # оплачено, когда собственник был «без НДС»
    db = _FakeDB([payment], owner_vat="vat5")
    assert await mark_closing_receipt_due(db, payment.application_id) is payment
    assert db.admin_titles() == ["НДС собственника изменился после оплаты"]
    same = _FakeDB([payment := _payment()], owner_vat="none")
    assert await mark_closing_receipt_due(same, payment.application_id) is payment
    assert same.admin_titles() == []


@pytest.mark.asyncio
async def test_second_entry_after_dispute_does_not_queue_again() -> None:
    payment = _payment(closing_receipt_status=SENT)
    db = _FakeDB([payment])
    assert await mark_closing_receipt_due(db, payment.application_id) is None
    assert payment.closing_receipt_status == SENT


@pytest.mark.asyncio
async def test_no_paid_payment_with_receipt_means_nothing_to_close() -> None:
    assert await mark_closing_receipt_due(_FakeDB([]), uuid4()) is None


@pytest.mark.asyncio
async def test_double_payment_closes_latest_and_warns_admin() -> None:
    application_id = uuid4()
    older = _payment(application_id=application_id, paid_at=_now() - timedelta(days=1))
    latest = _payment(application_id=application_id, paid_at=_now())
    # Строки отдаём в «неправильном» порядке: выбор последней не должен зависеть от него.
    db = _FakeDB([older, latest])
    assert await mark_closing_receipt_due(db, application_id) is latest
    assert older.closing_receipt_status is None
    assert db.admin_titles() == ["По заявке несколько оплат"]


# ============================================================
# Отправка
# ============================================================


class _FakeBank:
    def __init__(self, error: Exception | None = None, terminal_key: str = TERMINAL):
        self.error = error
        self.terminal_key = terminal_key
        self.sent: list[dict] = []

    async def send_closing_receipt(self, *, payment_id, receipt):
        self.sent.append({"payment_id": payment_id, "receipt": receipt})
        if self.error:
            raise self.error


@pytest.fixture
def sending(monkeypatch):
    state = SimpleNamespace(bank=_FakeBank(), claim=True, claims=0)
    monkeypatch.setattr(tbank_receipts, "get_tbank_service", lambda: state.bank)

    async def fake_claim(_db, _payment_id, _now):
        state.claims += 1
        return state.claim

    monkeypatch.setattr(tbank_receipts, "_claim", fake_claim)
    return state


@pytest.mark.asyncio
async def test_closing_receipt_sent(sending) -> None:
    payment = _payment(closing_receipt_status="sending")
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == SENT
    [call] = sending.bank.sent
    assert call["payment_id"] == "9287980194"
    assert call["receipt"]["Items"][0]["PaymentMethod"] == "full_payment"
    assert payment.closing_receipt_status == SENT
    assert payment.closing_receipt_at is not None
    assert db.admin_titles() == []


@pytest.mark.asyncio
async def test_not_claimed_means_someone_else_sends(sending) -> None:
    sending.claim = False
    payment = _payment(closing_receipt_status="sending")
    assert await send_closing_receipt(_FakeDB([payment]), payment.id) is None
    assert sending.bank.sent == []


@pytest.mark.asyncio
async def test_explicit_refusal_is_retryable_and_quiet_until_last_attempt(sending) -> None:
    sending.bank.error = TBankError("Касса недоступна", error_code="1051")
    payment = _payment(closing_receipt_status="sending", closing_receipt_attempts=1)
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == FAILED
    assert "Касса недоступна" in payment.closing_receipt_error
    assert db.admin_titles() == []  # крон ещё повторит


@pytest.mark.asyncio
async def test_refusal_on_last_attempt_alerts_admin(sending, monkeypatch) -> None:
    monkeypatch.setattr(tbank_receipts.settings, "tbank_closing_receipt_max_attempts", 3)
    sending.bank.error = TBankError("Касса недоступна", error_code="1051")
    payment = _payment(closing_receipt_status="sending", closing_receipt_attempts=3)
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == FAILED
    assert db.admin_titles() == ["Закрывающий чек не отправлен"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [TBankError("Т-Банк недоступен (SendClosingReceipt): ReadTimeout"), TBankError("сбой", error_code="9999")],
)
async def test_ambiguous_failure_is_unknown_and_never_retried_blindly(sending, error) -> None:
    # Банк мог чек и принять: повтор пробил бы второй «полный расчёт».
    sending.bank.error = error
    payment = _payment(closing_receipt_status="sending")
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == UNKNOWN
    assert db.admin_titles() == ["Проверьте закрывающий чек"]


@pytest.mark.asyncio
async def test_foreign_terminal_payment_is_left_to_admin(sending) -> None:
    payment = _payment(closing_receipt_status="sending", provider_account="OLDDEMO")
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == FAILED
    assert sending.bank.sent == []
    assert payment.closing_receipt_attempts >= tbank_receipts.settings.tbank_closing_receipt_max_attempts
    assert db.admin_titles() == ["Закрывающий чек не отправлен"]


@pytest.mark.asyncio
async def test_not_configured_does_nothing(monkeypatch) -> None:
    from app.services.tbank_acquiring import TBankNotConfigured

    def boom():
        raise TBankNotConfigured("нет ключей")

    monkeypatch.setattr(tbank_receipts, "get_tbank_service", boom)
    assert await send_closing_receipt(_FakeDB([]), uuid4()) is None


# ============================================================
# Выдача документов в рабочем процессе заявки
# ============================================================


@pytest.mark.asyncio
async def test_approving_documents_queues_closing_receipt(monkeypatch) -> None:
    from app.enums import ApplicationStatus, UserRole
    from app.services import application_workflow
    from test_application_workflow import FakeWorkflowSession, make_application

    calls: list = []

    async def fake_mark(_db, application_id):
        calls.append(application_id)

    monkeypatch.setattr(application_workflow, "mark_closing_receipt_due", fake_mark)
    application = make_application(status=ApplicationStatus.DOCUMENTS_REVIEW, created_by=uuid4())
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN.value, provider_id=None)
    await application_workflow.apply_application_action(
        db=FakeWorkflowSession(application), application_id=application.id,
        action="approve_documents", user=admin,
    )
    assert application.status == ApplicationStatus.READY_FOR_CLIENT.value
    assert calls == [application.id]


@pytest.mark.asyncio
async def test_other_transitions_do_not_touch_receipts(monkeypatch) -> None:
    from app.enums import ApplicationStatus, UserRole
    from app.services import application_workflow
    from test_application_workflow import FakeWorkflowSession, make_application

    calls: list = []

    async def fake_mark(_db, application_id):
        calls.append(application_id)

    monkeypatch.setattr(application_workflow, "mark_closing_receipt_due", fake_mark)
    application = make_application(status=ApplicationStatus.DOCUMENTS_REVIEW, created_by=uuid4())
    admin = SimpleNamespace(id=uuid4(), role=UserRole.ADMIN.value, provider_id=None)
    await application_workflow.apply_application_action(
        db=FakeWorkflowSession(application), application_id=application.id,
        action="request_document_revision", user=admin,
    )
    assert calls == []


@pytest.mark.asyncio
async def test_workflow_router_sends_receipt_right_after_commit(monkeypatch) -> None:
    from fastapi import BackgroundTasks

    from app.enums import ApplicationStatus
    from app.routers import workflow as workflow_router
    from app.schemas.workflow import ApplicationActionResult

    application_id = uuid4()

    async def fake_apply(**_kw):
        return ApplicationActionResult(
            application_id=application_id, status=ApplicationStatus.READY_FOR_CLIENT, available_actions=[]
        )

    class _DB:
        committed = False

        async def commit(self):
            _DB.committed = True

    monkeypatch.setattr(workflow_router, "apply_application_action", fake_apply)
    background = BackgroundTasks()
    await workflow_router.run_application_action(
        application_id=application_id, action="approve_documents", background=background,
        db=_DB(), user=SimpleNamespace(),
    )
    assert _DB.committed
    [task] = background.tasks
    assert task.func is workflow_router.send_due_for_application
    assert task.args == (application_id,)


# ============================================================
# Ревизия: SQL захвата и фильтров (на скомпилированном для Postgres запросе)
# ============================================================

from sqlalchemy.dialects import postgresql  # noqa: E402


class _RecordingDB(_FakeDB):
    """Запоминает запросы и порядок execute/commit; на UPDATE … RETURNING отдаёт id."""

    def __init__(self, rows=(), returning=()):
        super().__init__(rows)
        self.returning = list(returning)
        self.statements: list = []
        self.log: list[str] = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        self.log.append("execute")
        if getattr(stmt, "is_update", False):
            rows = list(self.returning)
            return SimpleNamespace(
                scalar_one_or_none=lambda: rows[0] if rows else None,
                scalars=lambda: SimpleNamespace(all=lambda: rows),
            )
        if getattr(stmt, "is_select", False) and stmt.column_descriptions[0].get("name") == "id":
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [p.id for p in self.rows]))
        return await super().execute(stmt)

    async def commit(self):
        self.log.append("commit")
        await super().commit()

    async def get(self, _model, key):
        return next((p for p in self.rows if p.id == key), None)


def _sql(stmt) -> tuple[str, dict]:
    compiled = stmt.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


@pytest.mark.asyncio
async def test_claim_is_one_conditional_update_committed_before_the_bank(monkeypatch) -> None:
    from app.services.tbank_receipts import _claim

    monkeypatch.setattr(tbank_receipts.settings, "tbank_closing_receipt_max_attempts", 5)
    payment_id = uuid4()
    now = _now()
    db = _RecordingDB(returning=[payment_id])
    assert await _claim(db, payment_id, now)
    assert db.log == ["execute", "commit"]  # захват фиксируется ДО похода в банк
    sql, params = _sql(db.statements[0])
    assert sql.startswith("UPDATE payments SET")
    assert "RETURNING payments.id" in sql
    # Занимаем только то, что можно отправлять: due или failed с попытками в запасе.
    statuses = {v for k, v in params.items() if k.startswith("closing_receipt_status")}
    assert statuses == {"sending", "due", "failed"}  # sending — в SET, due/failed — в WHERE
    assert "unknown" not in params.values()
    import re

    limit_param = re.search(r"closing_receipt_attempts < %\((\w+)\)s", sql).group(1)
    assert params[limit_param] == 5  # лимит попыток — в WHERE
    step_param = re.search(r"closing_receipt_attempts \+ %\((\w+)\)s", sql).group(1)
    assert params[step_param] == 1  # каждая попытка считается
    assert params["closing_receipt_at"] == now  # по нему ловятся зависшие отправки
    # Только оплаченный, с настоящим чеком предоплаты, без частичных возвратов.
    assert params["status_1"] == "succeeded"
    assert "jsonb_typeof(payments.receipt)" in sql
    assert "payments.refunded_kopeks = " in sql
    assert "payments.provider_status IS DISTINCT FROM" in sql


@pytest.mark.asyncio
async def test_claim_that_found_nothing_still_releases_the_connection() -> None:
    from app.services.tbank_receipts import _claim

    db = _RecordingDB(returning=[])
    assert not await _claim(db, uuid4(), _now())
    assert db.log == ["execute", "commit"]


@pytest.mark.asyncio
async def test_resend_queue_never_picks_unknown_or_sending() -> None:
    from app.services.tbank_receipts import closing_receipts_to_send

    db = _RecordingDB()
    await closing_receipts_to_send(db, limit=10)
    sql, params = _sql(db.statements[0])
    statuses = {v for k, v in params.items() if k.startswith("closing_receipt_status")}
    assert statuses == {"due", "failed"}
    assert "jsonb_typeof(payments.receipt)" in sql and "IS DISTINCT FROM" in sql


@pytest.mark.asyncio
async def test_stale_sending_becomes_unknown_with_one_alert_each() -> None:
    from app.services.tbank_receipts import expire_stale_sending

    stuck = [_payment(closing_receipt_status="unknown"), _payment(closing_receipt_status="unknown")]
    db = _RecordingDB(rows=stuck, returning=[p.id for p in stuck])
    now = _now()
    assert await expire_stale_sending(db, now) == 2
    sql, params = _sql(db.statements[0])
    assert params["closing_receipt_status"] == "unknown"  # SET
    assert params["closing_receipt_status_1"] == "sending"  # WHERE
    assert params["closing_receipt_at_1"] == now - tbank_receipts.SENDING_STALE_AFTER
    assert db.admin_titles() == ["Проверьте закрывающий чек"] * 2


@pytest.mark.asyncio
async def test_send_goes_to_bank_only_after_the_claim_is_committed(monkeypatch) -> None:
    payment = _payment(closing_receipt_status="sending")
    db = _RecordingDB(rows=[payment], returning=[payment.id])
    seen_commits: list[int] = []

    class _Bank(_FakeBank):
        async def send_closing_receipt(self, *, payment_id, receipt):
            seen_commits.append(db.commits)

    monkeypatch.setattr(tbank_receipts, "get_tbank_service", lambda: _Bank())
    assert await send_closing_receipt(db, payment.id) == SENT
    assert seen_commits == [1]


# ============================================================
# Ревизия: «запрос точно не ушёл» — не unknown, а повтор кроном
# ============================================================


@pytest.mark.asyncio
async def test_open_breaker_returns_receipt_to_queue_without_alert(monkeypatch) -> None:
    from app.services.dadata import CircuitBreaker
    from app.services.tbank_acquiring import TBankClient, TBankService

    breaker = CircuitBreaker(failure_threshold=1, recovery_seconds=600)
    breaker.record_failure()
    service = TBankService(
        TBankClient(terminal_key=TERMINAL, password="p", base_url="https://x/v2", timeout=1), breaker
    )
    monkeypatch.setattr(tbank_receipts, "get_tbank_service", lambda: service)

    async def claimed(*_a):
        return True

    monkeypatch.setattr(tbank_receipts, "_claim", claimed)
    payment = _payment(closing_receipt_status="sending", closing_receipt_attempts=2)
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == DUE
    assert payment.closing_receipt_status == DUE
    assert payment.closing_receipt_attempts == 1  # попытка не засчитана
    assert db.admin_titles() == []


@pytest.mark.asyncio
async def test_not_sent_error_is_retried_not_unknown(sending) -> None:
    sending.bank.error = TBankError("Т-Банк недоступен: ConnectError", not_sent=True)
    payment = _payment(closing_receipt_status="sending", closing_receipt_attempts=1)
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == DUE
    assert db.admin_titles() == []


@pytest.mark.asyncio
async def test_refusal_one_before_limit_stays_quiet(sending, monkeypatch) -> None:
    monkeypatch.setattr(tbank_receipts.settings, "tbank_closing_receipt_max_attempts", 3)
    sending.bank.error = TBankError("Касса недоступна", error_code="1051")
    payment = _payment(closing_receipt_status="sending", closing_receipt_attempts=2)
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == FAILED
    assert db.admin_titles() == []


@pytest.mark.asyncio
async def test_broken_receipt_snapshot_never_hangs_in_sending(sending) -> None:
    payment = _payment(closing_receipt_status="sending", receipt={"oops": 1})
    db = _FakeDB([payment])
    assert await send_closing_receipt(db, payment.id) == FAILED
    assert sending.bank.sent == []
    assert db.admin_titles() == ["Закрывающий чек не отправлен"]


# ============================================================
# Ревизия: один закрывающий чек на заявку, частичный возврат
# ============================================================


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [SENT, "sending", UNKNOWN, FAILED, DUE])
async def test_reentry_never_queues_a_second_receipt(status) -> None:
    payment = _payment(closing_receipt_status=status)
    db = _FakeDB([payment])
    assert await mark_closing_receipt_due(db, payment.application_id) is None
    assert payment.closing_receipt_status == status
    assert db.admin_titles() == []


@pytest.mark.asyncio
async def test_new_payment_after_closed_one_gets_no_second_receipt() -> None:
    # Спор → повторная оплата → снова «Готово»: закрывающий уже был по первой оплате.
    application_id = uuid4()
    closed = _payment(application_id=application_id, closing_receipt_status=SENT,
                      paid_at=_now() - timedelta(days=3))
    new = _payment(application_id=application_id, paid_at=_now())
    db = _FakeDB([new, closed])
    assert await mark_closing_receipt_due(db, application_id) is None
    assert new.closing_receipt_status is None


@pytest.mark.asyncio
async def test_payment_created_without_receipt_is_not_closed() -> None:
    payment = _payment(receipt=None)
    assert await mark_closing_receipt_due(_FakeDB([payment]), payment.application_id) is None
    assert payment.closing_receipt_status is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kw", [{"provider_status": "PARTIAL_REFUNDED"}, {"refunded_kopeks": 100_000}]
)
async def test_partially_refunded_payment_is_left_to_the_cabinet(kw) -> None:
    payment = _payment(**kw)
    db = _FakeDB([payment])
    assert await mark_closing_receipt_due(db, payment.application_id) is None
    assert payment.closing_receipt_status == FAILED
    assert payment.closing_receipt_attempts >= tbank_receipts.settings.tbank_closing_receipt_max_attempts
    assert db.admin_titles() == ["Закрывающий чек — вручную"]


def test_receipt_column_writes_none_as_sql_null() -> None:
    # Иначе None превращался в JSON null, и «receipt IS NOT NULL» находил платёж без чека.
    assert Payment.__table__.c.receipt.type.none_as_null is True


# ============================================================
# Ревизия: возвраты и отказы кассы
# ============================================================


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "alerted"),
    [(SENT, True), ("sending", True), (UNKNOWN, True), (None, False), (DUE, False), (FAILED, False)],
)
async def test_refund_alert_when_closing_receipt_may_exist(status, alerted) -> None:
    from app.services.tbank_receipts import alert_if_closing_receipt_may_exist

    payment = _payment(closing_receipt_status=status)
    db = _FakeDB([payment])
    await alert_if_closing_receipt_may_exist(db, payment)
    assert db.admin_titles() == (["Проверьте чек возврата"] if alerted else [])


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({"Receipt": {"Items": [{"PaymentMethod": "full_payment"}]}}, True),
        ({"Receipt": {"Items": [{"PaymentMethod": "full_prepayment"}]}}, False),
        ({}, None),
        ({"Receipt": "мусор"}, None),
    ],
)
def test_which_receipt_the_notification_is_about(body, expected) -> None:
    from app.services.tbank_receipts import receipt_notification_is_closing

    assert receipt_notification_is_closing(body) is expected
