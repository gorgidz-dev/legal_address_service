"""Фото показывается, а не скачивается — и одинаково при любом хранилище.

Локальная ветка отдавала `FileResponse(filename=...)`, то есть с
`Content-Disposition: attachment`: в дев-режиме картинка сохранялась на диск
вместо того, чтобы отрисоваться на странице. На проде (S3) поведение было
другим — и это тот самый класс расхождений local/S3, который здесь уже дважды
приводил к багам, видимым только в одном из режимов.

Поэтому проверяем не «локальная ветка чинена», а «обе ветки отвечают
одинаково»: различаться они должны только источником байтов.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.routers.address_photos as photos
from app.enums import AddressPhotoModerationStatus
from app.services.storage import LocalObjectStorage, S3ObjectStorage

PAYLOAD = b"\xff\xd8\xff\xe0 fake jpeg"


def _photo(status=AddressPhotoModerationStatus.APPROVED, filename="Фасад дома.jpg"):
    return SimpleNamespace(
        id=uuid4(),
        address_id=uuid4(),
        storage_key="addresses/x/photos/abc/photo.jpg",
        original_filename=filename,
        content_type="image/jpeg",
        moderation_status=status.value,
    )


class _FakeS3(S3ObjectStorage):
    """Тот же класс для isinstance, но без боевого клиента."""

    def __init__(self) -> None:  # noqa: D107 - намеренно без super()
        self.bucket = "test"

    def read_bytes(self, key: str) -> bytes:
        return PAYLOAD


@pytest.fixture()
def local_storage(tmp_path, monkeypatch):
    photo = _photo()
    target = tmp_path / photo.storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(PAYLOAD)
    storage = LocalObjectStorage(root=tmp_path)
    monkeypatch.setattr(photos, "get_object_storage", lambda: storage)
    return photo


@pytest.fixture()
def s3_storage(monkeypatch):
    monkeypatch.setattr(photos, "get_object_storage", lambda: _FakeS3())
    return _photo()


# --- главное: картинка отрисовывается ---


def test_local_photo_is_shown_not_downloaded(local_storage):
    response = photos._serve_stored_photo(local_storage)
    disposition = response.headers.get("content-disposition", "")
    assert "attachment" not in disposition, disposition
    assert "inline" in disposition, disposition


def test_local_photo_keeps_its_filename_for_save_as(local_storage):
    disposition = photos._serve_stored_photo(local_storage).headers.get(
        "content-disposition", ""
    )
    # Кириллица уезжает в RFC 5987 — так же, как в скачивании документов.
    assert "filename" in disposition
    assert disposition.encode("latin-1")


def test_s3_photo_is_shown_not_downloaded(s3_storage):
    disposition = photos._serve_stored_photo(s3_storage).headers.get(
        "content-disposition", ""
    )
    assert "attachment" not in disposition, disposition


# --- ветки не расходятся ---


def _both_branches(tmp_path, monkeypatch, photo):
    """Один и тот же снимок через оба хранилища — для сравнения ответов.

    Две фикстуры сразу тут не годятся: обе подменяют get_object_storage, и
    вторая незаметно перебивает первую — «локальная» ветка на самом деле
    уходила бы в S3, а тест продолжал зеленеть.
    """
    target = tmp_path / photo.storage_key
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(PAYLOAD)

    monkeypatch.setattr(
        photos, "get_object_storage", lambda: LocalObjectStorage(root=tmp_path)
    )
    local = photos._serve_stored_photo(photo)
    monkeypatch.setattr(photos, "get_object_storage", lambda: _FakeS3())
    remote = photos._serve_stored_photo(photo)
    return local, remote


def test_both_backends_agree_on_cache_control(tmp_path, monkeypatch):
    local, remote = _both_branches(tmp_path, monkeypatch, _photo())
    assert local.headers.get("cache-control") == remote.headers.get("cache-control")


def test_neither_backend_forces_a_download(tmp_path, monkeypatch):
    """Главный сторож расхождения: скачивание не должно вернуться в одну ветку."""
    local, remote = _both_branches(tmp_path, monkeypatch, _photo())
    for name, response in (("local", local), ("s3", remote)):
        assert "attachment" not in response.headers.get("content-disposition", ""), name


def test_both_backends_agree_on_media_type(tmp_path, monkeypatch):
    local, remote = _both_branches(tmp_path, monkeypatch, _photo())
    assert local.media_type == remote.media_type == "image/jpeg"


# --- кеш только для публичного ---


def test_approved_photo_is_cacheable():
    assert photos.photo_cache_control(_photo(AddressPhotoModerationStatus.APPROVED)) == (
        "public, max-age=3600"
    )


@pytest.mark.parametrize(
    "status",
    [AddressPhotoModerationStatus.PENDING, AddressPhotoModerationStatus.REJECTED],
)
def test_unapproved_photo_is_not_cached_by_proxies(status):
    """Иначе прокси однажды отдаст неодобренное фото анониму по той же ссылке."""
    header = photos.photo_cache_control(_photo(status))
    assert "public" not in header
    assert "no-store" in header
