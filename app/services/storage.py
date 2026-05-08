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


def resolve_storage_file(path_value: str, *, project_root: Path = PROJECT_ROOT) -> Path:
    candidate = (project_root / path_value).resolve()
    storage_root = (project_root / "storage").resolve()
    if storage_root not in candidate.parents and candidate != storage_root:
        raise ValueError("Можно скачивать только файлы из storage")
    if not candidate.is_file():
        raise FileNotFoundError(f"Файл не найден: {path_value}")
    return candidate
