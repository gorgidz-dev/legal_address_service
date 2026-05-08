from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.schemas.client import DaDataLookupResponse


def initials_from_name(full_name: str | None) -> str | None:
    if not full_name:
        return None
    parts = full_name.split()
    if len(parts) < 2:
        return full_name
    surname = parts[0]
    initials = " ".join(f"{part[0]}." for part in parts[1:] if part)
    return f"{surname} {initials}".strip()


def signatory_genitive_fallback(position: str | None, name: str | None) -> str | None:
    parts = [part for part in (position, name) if part]
    return " ".join(parts) if parts else None


def client_values_from_dadata(result: DaDataLookupResponse) -> dict[str, Any]:
    return {
        "inn": result.inn,
        "kpp": result.kpp,
        "ogrn": result.ogrn,
        "okved_main_code": result.okved_main_code,
        "okved_main_name": result.okved_main_name,
        "full_name": result.full_name,
        "short_name": result.short_name,
        "legal_address": result.legal_address,
        "kladr_id": result.kladr_id,
        "signatory_name": result.signatory_name,
        "signatory_position": result.signatory_position,
        "signatory_basis": "Устава",
        "signatory_name_genitive": signatory_genitive_fallback(
            result.signatory_position,
            result.signatory_name,
        ),
        "signatory_position_genitive": result.signatory_position,
        "signatory_initials": initials_from_name(result.signatory_name),
        "egrul_status": result.egrul_status.value,
        "last_dadata_refresh_at": datetime.now(timezone.utc),
    }
