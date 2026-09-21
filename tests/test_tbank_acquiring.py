"""Клиент Т-Банка: подпись Token, разбор ответов, предохранитель, TLS-бандл.

Эталоны подписи — из документации (docs/tbank-acquiring.md §2). Итоговый JSON
на странице «Токен» с хешем не согласован, поэтому проверяем по массиву пар.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography import x509

from app.services import tbank_acquiring as tb
from app.services.dadata import CircuitBreaker
from app.services.tbank_acquiring import (
    TBankClient,
    TBankError,
    TBankService,
    make_token,
    tbank_ssl_context,
    verify_notification_token,
)

PASSWORD = "11111111111111"


# ============================================================
# Подпись
# ============================================================


def test_token_matches_documentation_vector() -> None:
    params = {
        "TerminalKey": "MerchantTerminalKey",
        "Amount": "19200",
        "OrderId": "00000",
        "Description": "Подарочная карта на 1000 рублей",
    }
    # Опубликованный результат: 72dd466f8ace0a37a1… — проверяем префикс из документации.
    assert make_token(params, PASSWORD).startswith("72dd466f8ace0a37")


def test_token_skips_nested_objects_token_and_none() -> None:
    base = {"TerminalKey": "T", "Amount": 100, "OrderId": "o1"}
    with_extras = dict(
        base,
        Token="whatever",
        Receipt={"Items": [{"Name": "x"}]},
        DATA={"k": "v"},
        Shops=[{"ShopCode": "1"}],
        Description=None,
    )
    assert make_token(with_extras, PASSWORD) == make_token(base, PASSWORD)


def test_token_serialises_booleans_lowercase_and_ints_plainly() -> None:
    body = {"Success": True, "Amount": 10000, "PaymentId": 123, "TerminalKey": "T"}
    # Порядок ключей: Amount, Password, PaymentId, Success, TerminalKey.
    expected = hashlib.sha256(f"10000{PASSWORD}123trueT".encode("utf-8")).hexdigest()
    assert make_token(body, PASSWORD) == expected


def test_token_sort_is_case_sensitive_like_the_bank() -> None:
    # Pan < Password < PaymentId (порядок кодов символов, как у Java TreeMap).
    body = {"PaymentId": "9", "Pan": "4300****0777", "TerminalKey": "T"}
    expected = hashlib.sha256(f"4300****0777{PASSWORD}9T".encode("utf-8")).hexdigest()
    assert make_token(body, PASSWORD) == expected


def _signed_notification(**overrides) -> dict:
    body = {
        "TerminalKey": "1234567890DEMO",
        "OrderId": "000000",
        "Success": True,
        "Status": "CONFIRMED",
        "PaymentId": 13660,
        "ErrorCode": "0",
        "Amount": 1111,
        "Pan": "200000******0000",
        "Data": {"DrPaymentId": "x"},  # вложенный объект в подпись не входит
    }
    body.update(overrides)
    body["Token"] = make_token(body, PASSWORD)
    return body


def test_verify_notification_accepts_signed_body() -> None:
    assert verify_notification_token(_signed_notification(), PASSWORD)


def test_verify_notification_accepts_uppercase_token() -> None:
    body = _signed_notification()
    body["Token"] = body["Token"].upper()
    assert verify_notification_token(body, PASSWORD)


def test_verify_notification_rejects_tampered_amount() -> None:
    body = _signed_notification()
    body["Amount"] = 1
    assert not verify_notification_token(body, PASSWORD)


def test_verify_notification_rejects_missing_or_foreign_token() -> None:
    body = _signed_notification()
    assert not verify_notification_token({k: v for k, v in body.items() if k != "Token"}, PASSWORD)
    assert not verify_notification_token(body, "другой-пароль")


def test_verify_notification_uses_every_arrived_field() -> None:
    # Поле, которого нет в таблице документации (RebillId), тоже подписано банком.
    body = _signed_notification(RebillId="777")
    assert verify_notification_token(body, PASSWORD)
    body["RebillId"] = "778"
    assert not verify_notification_token(body, PASSWORD)


# ============================================================
# HTTP: разбор ответов
# ============================================================


def _patch_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient
    seen: list[dict] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        seen.append({"url": str(request.url), "json": json.loads(request.content or b"{}")})
        return handler(request)

    monkeypatch.setattr(
        tb.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(_handler), timeout=kw.get("timeout")),
    )
    return seen


def _client() -> TBankClient:
    return TBankClient(
        terminal_key="1234567890DEMO",
        password=PASSWORD,
        base_url="https://securepay.tinkoff.ru/v2",
        timeout=5,
    )


@pytest.mark.asyncio
async def test_init_sends_signed_request_and_parses_response(monkeypatch) -> None:
    seen = _patch_transport(
        monkeypatch,
        lambda _r: httpx.Response(200, json={
            "Success": True, "ErrorCode": "0", "Status": "NEW",
            "PaymentId": 9287980194, "PaymentURL": "https://pay.tbank.ru/new/abc",
        }),
    )
    due = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
    result = await _client().init(
        amount_kopeks=150000,
        order_id="order-1",
        description="Юр. адрес: " + "x" * 300,
        notification_url="https://uradres.net/api/v1/webhooks/tbank/notification",
        success_url="https://uradres.net/?payment=success",
        fail_url="https://uradres.net/?payment=fail",
        redirect_due=due,
        receipt={"Taxation": "usn_income", "Items": []},
    )
    sent = seen[0]["json"]
    assert seen[0]["url"] == "https://securepay.tinkoff.ru/v2/Init"
    assert sent["TerminalKey"] == "1234567890DEMO"
    assert sent["Amount"] == 150000
    assert sent["PayType"] == "O"
    assert len(sent["Description"]) == 140
    # UTC 12:00 → московские 15:00, формат из документации.
    assert sent["RedirectDueDate"] == "2026-09-21T15:00:00+03:00"
    # Токен посчитан без Receipt и сходится с независимым расчётом.
    assert sent["Token"] == make_token({k: v for k, v in sent.items() if k != "Token"}, PASSWORD)
    # PaymentId отдаём строкой: как число он теряет точность в JS.
    assert result.payment_id == "9287980194"
    assert result.payment_url == "https://pay.tbank.ru/new/abc"


@pytest.mark.asyncio
async def test_business_error_raises_with_code(monkeypatch) -> None:
    _patch_transport(
        monkeypatch,
        lambda _r: httpx.Response(200, json={
            "Success": False, "ErrorCode": "325", "Message": "Неверные параметры.",
            "Details": "Транзакция не найдена.",
        }),
    )
    with pytest.raises(TBankError) as exc:
        await _client().get_state(payment_id="1")
    assert exc.value.error_code == "325"
    assert "Транзакция не найдена" in str(exc.value)


@pytest.mark.asyncio
async def test_http_500_is_an_error(monkeypatch) -> None:
    _patch_transport(
        monkeypatch,
        lambda _r: httpx.Response(500, json={"Success": False, "ErrorCode": "9999", "Message": "Сбой"}),
    )
    with pytest.raises(TBankError) as exc:
        await _client().get_state(payment_id="1")
    assert exc.value.error_code == "9999"


@pytest.mark.asyncio
async def test_cancel_parses_amounts(monkeypatch) -> None:
    seen = _patch_transport(
        monkeypatch,
        lambda _r: httpx.Response(200, json={
            "Success": True, "ErrorCode": "0", "Status": "PARTIAL_REFUNDED",
            "OriginalAmount": 150000, "NewAmount": 100000, "PaymentId": "1",
        }),
    )
    result = await _client().cancel(
        payment_id="1", amount_kopeks=50000, external_request_id="refund:x:0:50000"
    )
    assert seen[0]["json"]["Amount"] == 50000
    assert seen[0]["json"]["ExternalRequestId"] == "refund:x:0:50000"
    assert result.status == "PARTIAL_REFUNDED"
    assert result.new_amount_kopeks == 100000


@pytest.mark.asyncio
async def test_business_errors_do_not_trip_the_breaker(monkeypatch) -> None:
    _patch_transport(
        monkeypatch,
        lambda _r: httpx.Response(200, json={"Success": False, "ErrorCode": "325", "Message": "x"}),
    )
    service = TBankService(_client(), CircuitBreaker(failure_threshold=1, recovery_seconds=60))
    for _ in range(3):
        with pytest.raises(TBankError) as exc:
            await service.get_state(payment_id="1")
        assert exc.value.error_code == "325"  # не «предохранитель открыт»


@pytest.mark.asyncio
async def test_network_errors_trip_the_breaker(monkeypatch) -> None:
    def boom(_r):
        raise httpx.ConnectError("нет сети")

    _patch_transport(monkeypatch, boom)
    service = TBankService(_client(), CircuitBreaker(failure_threshold=1, recovery_seconds=60))
    with pytest.raises(TBankError):
        await service.get_state(payment_id="1")
    with pytest.raises(TBankError, match="предохранитель"):
        await service.get_state(payment_id="1")


def test_demo_terminal_detection() -> None:
    assert _client().is_demo
    assert not TBankClient(
        terminal_key="1234567890", password="p", base_url="https://x", timeout=1
    ).is_demo


# ============================================================
# TLS: сертификаты НУЦ Минцифры
# ============================================================


def test_ssl_context_trusts_russian_ca_on_top_of_certifi() -> None:
    subjects = {
        dict(item[0] for item in cert["subject"]).get("commonName")
        for cert in tbank_ssl_context().get_ca_certs()
    }
    assert "Russian Trusted Root CA" in subjects
    # И публичные УЦ из certifi никуда не делись.
    assert len(subjects) > 50


def test_russian_sub_ca_is_not_about_to_expire() -> None:
    """Сторож: промежуточный сертификат Минцифры действует до 06.03.2027.

    Упал — пора обновить app/certs/russian_trusted_ca.pem с
    https://www.gosuslugi.ru/crt, иначе в день истечения оплата встанет.
    """
    certs = x509.load_pem_x509_certificates(tb._RUSSIAN_TRUSTED_CA.read_bytes())
    assert len(certs) == 2
    soonest = min(cert.not_valid_after_utc for cert in certs)
    assert soonest - datetime.now(timezone.utc) > timedelta(days=60), (
        f"Сертификат НУЦ истекает {soonest:%d.%m.%Y} — обновите app/certs/russian_trusted_ca.pem"
    )


def test_redirect_due_format_is_documented_shape() -> None:
    value = datetime(2026, 1, 31, 22, 30, tzinfo=timezone.utc).astimezone(tb._MSK).strftime(
        "%Y-%m-%dT%H:%M:%S+03:00"
    )
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+03:00", value)
    assert value == "2026-02-01T01:30:00+03:00"
