from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def create_package_zip(*, zip_path: Path, entries: list[tuple[Path, str]]) -> Path:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(zip_path, "w", compression=ZIP_DEFLATED) as zf:
        for source_path, archive_name in entries:
            if not source_path.exists():
                raise FileNotFoundError(f"Файл для ZIP не найден: {source_path}")
            zf.write(source_path, archive_name)
    return zip_path
