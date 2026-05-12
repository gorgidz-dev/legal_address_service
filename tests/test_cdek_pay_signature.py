"""Подпись CDEK Pay — round-trip-проверки против примера из их доки.

Пример из openapi.yaml для генерации платежного ордера:
    payment_order = {"pay_for": "Оплата за тест", "currency": "RUR", "pay_amount": 100}
    secret_key   = "secret_key_123"
    signature    = "1929EBCF234CB20EBC07F831EF42D7C9AEEB026B5D19A94427A9178915B94015"

Документ говорит «sort keys alphabetically» — для этих 3 полей порядок:
    currency, pay_amount, pay_for
И конкатенация значений через |:
    "RUR|100|Оплата за тест|secret_key_123"
"""
from __future__ import annotations

from app.services.cdek_pay import sign_payment_order, verify_callback_signature


def test_sign_simple_payment_order_matches_docs_example() -> None:
    signature = sign_payment_order(
        {"pay_for": "Оплата за тест", "currency": "RUR", "pay_amount": 100},
        "secret_key_123",
    )
    # See the example block in CDEK Pay API docs:
    # "RUR|100|Оплата за тест|secret_key_123" → SHA256 hex upper.
    assert signature == "1929EBCF234CB20EBC07F831EF42D7C9AEEB026B5D19A94427A9178915B94015"


def test_sign_with_receipt_details_flattens_nested_arrays() -> None:
    """Из доки: receipt_details.0.id, receipt_details.0.name, ... — flatten + ABC."""
    order = {
        "pay_for": "Оплата за тест",
        "currency": "RUR",
        "pay_amount": 5000,
        "receipt_details": [
            {"id": 10, "name": "test item 1", "price": 2000, "quantity": 2, "sum": 4000, "payment_object": 1},
            {"id": 23, "name": "test item 2", "price": 1000, "quantity": 1, "sum": 1000, "payment_object": 1},
        ],
    }
    signature = sign_payment_order(order, "secret_key_123")
    assert signature == "D933AC7EB72F372D3A2C1AF86AF82AA8EB2D20407E463A2656FB91AEDA9B2A50"


def test_verify_callback_accepts_correct_signature() -> None:
    payment = {"id": 123, "order_id": 456, "access_key": "abc", "pay_amount": 1000, "currency": "RUR"}
    secret = "k"
    sig = sign_payment_order(payment, secret)
    assert verify_callback_signature(payment, sig, secret) is True
    assert verify_callback_signature(payment, sig.lower(), secret) is True  # case-insensitive


def test_verify_callback_rejects_wrong_signature() -> None:
    payment = {"id": 123, "order_id": 456, "access_key": "abc", "pay_amount": 1000, "currency": "RUR"}
    assert verify_callback_signature(payment, "0" * 64, "k") is False
    assert verify_callback_signature(payment, "", "k") is False


def test_verify_callback_rejects_tampered_payload() -> None:
    payment = {"id": 123, "order_id": 456, "access_key": "abc", "pay_amount": 1000, "currency": "RUR"}
    sig = sign_payment_order(payment, "k")
    tampered = {**payment, "pay_amount": 9999}
    assert verify_callback_signature(tampered, sig, "k") is False
