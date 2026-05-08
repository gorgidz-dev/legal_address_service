from __future__ import annotations

from pathlib import Path

import pytest

from app.services.storage import resolve_storage_file


def test_resolve_storage_file_accepts_relative_storage_path(tmp_path: Path) -> None:
    file_path = tmp_path / "storage" / "generated" / "package.zip"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"zip")

    resolved = resolve_storage_file("storage/generated/package.zip", project_root=tmp_path)

    assert resolved == file_path


def test_resolve_storage_file_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="storage"):
        resolve_storage_file("../.env", project_root=tmp_path)
