from __future__ import annotations

from pathlib import Path

import pytest

from app.services.storage import LocalObjectStorage, object_storage_key, resolve_storage_file


def test_resolve_storage_file_accepts_relative_storage_path(tmp_path: Path) -> None:
    file_path = tmp_path / "storage" / "generated" / "package.zip"
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b"zip")

    resolved = resolve_storage_file("storage/generated/package.zip", project_root=tmp_path)

    assert resolved == file_path


def test_resolve_storage_file_rejects_path_traversal(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="storage"):
        resolve_storage_file("../.env", project_root=tmp_path)


def test_local_object_storage_writes_and_reads_namespaced_file(tmp_path: Path) -> None:
    storage = LocalObjectStorage(root=tmp_path / "cloud")

    result = storage.put_bytes(
        key="clients/client-1/payment/receipt.pdf",
        content=b"%PDF",
        content_type="application/pdf",
    )

    assert result.backend == "local"
    assert result.key == "clients/client-1/payment/receipt.pdf"
    assert storage.read_bytes(result.key) == b"%PDF"
    assert (tmp_path / "cloud" / result.key).is_file()


def test_object_storage_key_is_safe_and_client_scoped() -> None:
    key = object_storage_key(
        kind="payment_document",
        original_filename="../счёт №1.pdf",
        content_hash="a" * 64,
        client_id="client-1",
    )

    assert key == "clients/client-1/payment_document/aaaaaaaaaaaaaaaa/счет__1.pdf"
