from __future__ import annotations

"""
Валидаторы российских реквизитов с проверкой контрольных сумм.

Используются как Annotated-типы в Pydantic-схемах:
    inn: INNLegal  →  валидируется и при создании, и при чтении из БД.
"""
from typing import Annotated

from pydantic import AfterValidator


def _digits_only(s: str, *, name: str, length: int | tuple[int, ...]) -> str:
    if not s.isdigit():
        raise ValueError(f"{name}: должен состоять только из цифр")
    expected = (length,) if isinstance(length, int) else length
    if len(s) not in expected:
        exp = " или ".join(str(x) for x in expected)
        raise ValueError(f"{name}: должен быть {exp} знаков, получено {len(s)}")
    return s


def _inn10_checksum(s: str) -> bool:
    weights = [2, 4, 10, 3, 5, 9, 4, 6, 8]
    total = sum(int(s[i]) * weights[i] for i in range(9))
    return int(s[9]) == (total % 11) % 10


def _inn12_checksum(s: str) -> bool:
    w11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    w12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
    n11 = sum(int(s[i]) * w11[i] for i in range(10))
    n12 = sum(int(s[i]) * w12[i] for i in range(11))
    return int(s[10]) == (n11 % 11) % 10 and int(s[11]) == (n12 % 11) % 10


def validate_inn_legal(v: str) -> str:
    s = _digits_only(v, name="ИНН ЮЛ", length=10)
    if not _inn10_checksum(s):
        raise ValueError("ИНН: контрольная сумма не сошлась")
    return s


def validate_inn_any(v: str) -> str:
    s = _digits_only(v, name="ИНН", length=(10, 12))
    ok = _inn10_checksum(s) if len(s) == 10 else _inn12_checksum(s)
    if not ok:
        raise ValueError("ИНН: контрольная сумма не сошлась")
    return s


def validate_kpp(v: str) -> str:
    return _digits_only(v, name="КПП", length=9)


def _ogrn13_checksum(s: str) -> bool:
    return int(s[12]) == int(s[:12]) % 11 % 10


def _ogrn15_checksum(s: str) -> bool:
    return int(s[14]) == int(s[:14]) % 13 % 10


def validate_ogrn(v: str) -> str:
    s = _digits_only(v, name="ОГРН", length=13)
    if not _ogrn13_checksum(s):
        raise ValueError("ОГРН: контрольная сумма не сошлась")
    return s


def validate_ogrn_any(v: str) -> str:
    s = _digits_only(v, name="ОГРН/ОГРНИП", length=(13, 15))
    ok = _ogrn13_checksum(s) if len(s) == 13 else _ogrn15_checksum(s)
    if not ok:
        raise ValueError("ОГРН/ОГРНИП: контрольная сумма не сошлась")
    return s


def validate_bik(v: str) -> str:
    return _digits_only(v, name="БИК", length=9)


def validate_settlement_account(v: str) -> str:
    return _digits_only(v, name="Расчётный счёт", length=20)


def validate_corr_account(v: str) -> str:
    return _digits_only(v, name="Корр. счёт", length=20)


def validate_cadastral_number(v: str) -> str:
    parts = v.split(":")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        raise ValueError("Кадастровый номер: ожидается формат AA:BB:CCCCCCC:DD")
    return v


# Annotated-типы для удобной декларации полей в схемах
INNLegal = Annotated[str, AfterValidator(validate_inn_legal)]
INN = Annotated[str, AfterValidator(validate_inn_any)]
KPP = Annotated[str, AfterValidator(validate_kpp)]
OGRN = Annotated[str, AfterValidator(validate_ogrn)]
OGRNAny = Annotated[str, AfterValidator(validate_ogrn_any)]
BIK = Annotated[str, AfterValidator(validate_bik)]
SettlementAccount = Annotated[str, AfterValidator(validate_settlement_account)]
CorrAccount = Annotated[str, AfterValidator(validate_corr_account)]
CadastralNumber = Annotated[str, AfterValidator(validate_cadastral_number)]
