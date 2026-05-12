from __future__ import annotations

import pytest

from app.contacts import (
    ContactNameError,
    EmailFormatError,
    PhoneFormatError,
    normalize_contact_name,
    normalize_email,
    normalize_optional_phone,
    normalize_phone,
)


# ---- Phone -------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("+7 (916) 123-45-67", "+79161234567"),
        ("8 (916) 123-45-67", "+79161234567"),
        ("8-916-123-45-67", "+79161234567"),
        ("8 916 123 45 67", "+79161234567"),
        ("89161234567", "+79161234567"),
        ("79161234567", "+79161234567"),
        ("+79161234567", "+79161234567"),
        ("9161234567", "+79161234567"),
        ("+1 415-555-1234", "+14155551234"),
        ("+44 20 7946 0958", "+442079460958"),
    ],
)
def test_normalize_phone_handles_common_formats(raw: str, expected: str) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "abc",
        "123",  # too short
        "1234567890123456",  # 16 digits — too long
        "+0234567890",  # E.164 starts not with 0
    ],
)
def test_normalize_phone_rejects_invalid(raw: str) -> None:
    with pytest.raises(PhoneFormatError):
        normalize_phone(raw)


def test_normalize_optional_phone_passes_none_and_empty() -> None:
    assert normalize_optional_phone(None) is None
    assert normalize_optional_phone("") is None


def test_normalize_optional_phone_normalises_value() -> None:
    assert normalize_optional_phone("8 916 123-45-67") == "+79161234567"


# ---- Email -------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("USER@Example.COM", "user@example.com"),
        (" user@example.com ", "user@example.com"),
        ("User.Name+tag@Foo.Bar", "user.name+tag@foo.bar"),
    ],
)
def test_normalize_email_lowercases_and_trims(raw: str, expected: str) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "no-at-sign",
        "@no-local.com",
        "no-domain@",
        "spaces in@email.com",
        "x@x.x",  # TLD < 2 chars
    ],
)
def test_normalize_email_rejects_invalid(raw: str) -> None:
    with pytest.raises(EmailFormatError):
        normalize_email(raw)


# ---- Contact name ------------------------------------------------------------


def test_normalize_contact_name_trims_and_collapses_whitespace() -> None:
    assert normalize_contact_name("  Иван   Петрович   ") == "Иван Петрович"


def test_normalize_contact_name_rejects_short_or_empty() -> None:
    for raw in ("", " ", "X"):
        with pytest.raises(ContactNameError):
            normalize_contact_name(raw)


def test_normalize_contact_name_rejects_oversized() -> None:
    with pytest.raises(ContactNameError):
        normalize_contact_name("A" * 201)


# ---- Pydantic integration ----------------------------------------------------


def test_annotated_types_normalise_through_pydantic_model() -> None:
    from pydantic import BaseModel

    from app.contacts import ContactName, Email, OptionalPhone, Phone

    class Form(BaseModel):
        name: ContactName
        email: Email
        phone: Phone
        backup_phone: OptionalPhone = None

    form = Form(
        name="   Иван   Иванов  ",
        email="USER@Example.COM",
        phone="8 (916) 123-45-67",
        backup_phone="",
    )
    assert form.name == "Иван Иванов"
    assert form.email == "user@example.com"
    assert form.phone == "+79161234567"
    assert form.backup_phone is None
