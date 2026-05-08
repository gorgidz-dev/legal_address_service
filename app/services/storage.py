from __future__ import annotations

from pathlib import Path
from uuid import UUID


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = PROJECT_ROOT / "storage"
GENERATED_ROOT = STORAGE_ROOT / "generated"
EGRN_ROOT = STORAGE_ROOT / "egrn"
TEMPLATE_ROOT = STORAGE_ROOT / "templates"


def application_storage_dir(application_id: UUID | str) -> Path:
    return GENERATED_ROOT / str(application_id)


def egrn_storage_dir(address_id: UUID | str) -> Path:
    return EGRN_ROOT / str(address_id)


def template_storage_dir(kind: str) -> Path:
    return TEMPLATE_ROOT / kind


def relative_storage_url(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)
