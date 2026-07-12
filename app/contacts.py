"""Единый формат хранения контактов.

Каждое поле, прежде чем попасть в БД, проходит через нормализатор:

- **Телефон**: голые цифры → E.164. Российские форматы (10/11 цифр, с/без 8/+7)
  приводятся к `+7XXXXXXXXXX`. Международные — `+CC...` если был ведущий `+`.
- **Email**: trim + lowercase. Локальная часть НЕ трогается, только домен — это
  правильно по RFC 5321: домен case-insensitive, локальная часть может быть
  case-sensitive у некоторых провайдеров. Но на практике все мейнстрим-провайдеры
  не различают регистр в локали, и Гугл/Яндекс точно нет. Берём lowercase всю
  строку — это даёт надёжный uniqueness по индексу.
- **Имя**: trim + сжать пробелы.

Используется как Annotated-типы в Pydantic-схемах:

    contact_phone: Phone | None
    contact_email: Email
    contact_name: ContactName
"""
from __future__ import annotations

import re
from typing import Annotated, Optional

from pydantic import BeforeValidator


# ============================================================
# Phone
# ============================================================

_PHONE_DIGITS_RE = re.compile(r"\d")


class PhoneFormatError(ValueError):
    pass


def normalize_phone(raw: str) -> str:
    """Привести произвольный ввод к E.164.

    Примеры:
        "+7 (916) 123-45-67"  → "+79161234567"
        "8 916 123-45-67"     → "+79161234567"
        "9161234567"          → "+79161234567"
        "+1 415-555-1234"     → "+14155551234"
    """
    if raw is None:
        raise PhoneFormatError("Телефон обязателен")
    stripped = raw.strip()
    if not stripped:
        raise PhoneFormatError("Телефон не может быть пустым")

    had_plus = stripped.lstrip().startswith("+")
    digits = "".join(_PHONE_DIGITS_RE.findall(stripped))

    if not digits:
        raise PhoneFormatError("Телефон должен содержать хотя бы одну цифру")

    # Российские форматы:
    # 10 цифр (без кода страны) — добавляем +7
    # 11 цифр, начинающихся на 8 — заменяем 8 на 7
    # 11 цифр, начинающихся на 7 — добавляем +
    if not had_plus:
        if len(digits) == 10:
            digits = "7" + digits
        elif len(digits) == 11 and digits[0] == "8":
            digits = "7" + digits[1:]
        elif len(digits) == 11 and digits[0] == "7":
            pass  # ок
        else:
            raise PhoneFormatError(
                "Российский телефон ожидается из 10 или 11 цифр (с 7/8)"
            )

    # E.164: 8–15 цифр после +, начинается не с 0
    if not (8 <= len(digits) <= 15):
        raise PhoneFormatError(f"Длина номера должна быть 8–15 цифр, получено {len(digits)}")
    if digits[0] == "0":
        raise PhoneFormatError("Номер не может начинаться с 0 (после +)")

    return "+" + digits


# ============================================================
# Email
# ============================================================


class EmailFormatError(ValueError):
    pass


# Минимальная валидация: есть @, не пусто с обеих сторон, длина в пределах разумного.
# Полная RFC-валидация — задача EmailStr из pydantic, но мы сохраняем нормализацию.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def normalize_email(raw: str) -> str:
    if raw is None:
        raise EmailFormatError("E-mail обязателен")
    stripped = raw.strip().lower()
    if not stripped:
        raise EmailFormatError("E-mail не может быть пустым")
    if len(stripped) > 254:
        raise EmailFormatError("E-mail длиннее 254 символов")
    if not _EMAIL_RE.match(stripped):
        raise EmailFormatError("Неверный формат e-mail")
    return stripped


# ============================================================
# Contact name
# ============================================================


_WHITESPACE_RE = re.compile(r"\s+")


class ContactNameError(ValueError):
    pass


def normalize_contact_name(raw: str) -> str:
    if raw is None:
        raise ContactNameError("Имя обязательно")
    collapsed = _WHITESPACE_RE.sub(" ", raw.strip())
    if not collapsed:
        raise ContactNameError("Имя не может быть пустым")
    if len(collapsed) < 2:
        raise ContactNameError("Имя должно быть не короче 2 символов")
    if len(collapsed) > 200:
        raise ContactNameError("Имя длиннее 200 символов")
    return collapsed


# ============================================================
# Annotated-типы для схем
# ============================================================

# BeforeValidator используется чтобы нормализатор отработал ДО проверки длины/типа.
Phone = Annotated[str, BeforeValidator(normalize_phone)]
Email = Annotated[str, BeforeValidator(normalize_email)]
ContactName = Annotated[str, BeforeValidator(normalize_contact_name)]


def normalize_optional_phone(value):
    return normalize_phone(value) if value is not None and value != "" else None


def normalize_optional_email(value):
    return normalize_email(value) if value is not None and value != "" else None


def normalize_optional_contact_name(value):
    return normalize_contact_name(value) if value is not None and value != "" else None


OptionalPhone = Annotated[Optional[str], BeforeValidator(normalize_optional_phone)]
OptionalEmail = Annotated[Optional[str], BeforeValidator(normalize_optional_email)]
OptionalContactName = Annotated[Optional[str], BeforeValidator(normalize_optional_contact_name)]
