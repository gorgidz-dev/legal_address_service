from __future__ import annotations

"""Unit-тесты сервиса фотографий адреса (без БД)."""

import io
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image

from app.enums import AddressPhotoModerationStatus, UserRole
from app.services.address_photos import (
    MAX_DIMENSION,
    OUTPUT_CONTENT_TYPE,
    _ensure_address_owner_or_admin,
    process_image_bytes,
)


def _make_png_bytes(width: int, height: int, color: tuple[int, int, int] = (240, 100, 50)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def _make_rgba_png_bytes(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (width, height), (10, 200, 30, 128)).save(buffer, format="PNG")
    return buffer.getvalue()


# ------------------------ process_image_bytes ------------------------


def test_process_image_normalizes_to_jpeg() -> None:
    raw = _make_png_bytes(800, 600)

    processed = process_image_bytes(raw)

    assert processed.width == 800
    assert processed.height == 600
    # Сжатие гарантирует JPEG-сигнатуру.
    assert processed.content[:2] == b"\xff\xd8"


def test_process_image_resizes_only_when_larger_than_max() -> None:
    raw = _make_png_bytes(3200, 2400)

    processed = process_image_bytes(raw)

    # Длинная сторона ужимается до MAX_DIMENSION; пропорция сохраняется.
    assert max(processed.width, processed.height) == MAX_DIMENSION
    assert processed.width == MAX_DIMENSION
    assert processed.height == MAX_DIMENSION * 2400 // 3200


def test_process_image_does_not_upscale_small_images() -> None:
    raw = _make_png_bytes(320, 240)

    processed = process_image_bytes(raw)

    assert processed.width == 320
    assert processed.height == 240


def test_process_image_converts_rgba_to_rgb_with_white_background() -> None:
    raw = _make_rgba_png_bytes(400, 300)

    processed = process_image_bytes(raw)

    # JPEG не умеет alpha — поэтому Pillow прочитает результат как RGB.
    with Image.open(io.BytesIO(processed.content)) as img:
        assert img.mode == "RGB"
        assert img.size == (400, 300)


def test_process_image_rejects_non_image_bytes() -> None:
    with pytest.raises(HTTPException) as exc:
        process_image_bytes(b"definitely not an image")
    assert exc.value.status_code == 422


def test_process_image_output_content_type_is_jpeg() -> None:
    # Контракт: на выходе всегда JPEG. Это упрощает админ-UI: один MIME-тип
    # на все одобренные фотографии.
    assert OUTPUT_CONTENT_TYPE == "image/jpeg"


# ------------------------ _ensure_address_owner_or_admin ------------------------


def _user(role: str, provider_id=None):
    return SimpleNamespace(id=uuid4(), role=role, provider_id=provider_id)


def _address(provider_id):
    return SimpleNamespace(id=uuid4(), provider_id=provider_id)


def test_ensure_admin_can_access_any_address() -> None:
    admin = _user(UserRole.ADMIN.value, provider_id=None)
    address = _address(uuid4())
    _ensure_address_owner_or_admin(admin, address)  # не должно бросить


def test_ensure_owner_of_provider_can_access_own_address() -> None:
    provider_id = uuid4()
    owner = _user(UserRole.OWNER.value, provider_id=provider_id)
    address = _address(provider_id)
    _ensure_address_owner_or_admin(owner, address)  # не должно бросить


def test_ensure_owner_of_other_provider_gets_403() -> None:
    owner = _user(UserRole.OWNER.value, provider_id=uuid4())
    address = _address(uuid4())
    with pytest.raises(HTTPException) as exc:
        _ensure_address_owner_or_admin(owner, address)
    assert exc.value.status_code == 403


def test_ensure_client_cannot_access_address_photos_management() -> None:
    client = _user(UserRole.CLIENT.value, provider_id=None)
    address = _address(uuid4())
    with pytest.raises(HTTPException) as exc:
        _ensure_address_owner_or_admin(client, address)
    assert exc.value.status_code == 403


# ------------------------ enum sanity ------------------------


def test_moderation_status_enum_values_match_constraint() -> None:
    # Гарантируем, что миграция 0006 и enum не расходятся: эта тройка
    # значений жёстко закреплена в CHECK-констрейнте.
    assert {s.value for s in AddressPhotoModerationStatus} == {
        "pending",
        "approved",
        "rejected",
    }


# ------------------------ upload_address_photo: валидация ------------------------


class _FakeSession:
    """Минимальный фейк AsyncSession для проверки путей валидации."""

    def __init__(self, address, photo_count: int = 0):
        self._address = address
        self._photo_count = photo_count
        self.added = []
        self.flushed = False

    async def get(self, _model, _object_id):
        return self._address

    async def execute(self, _stmt):
        count = self._photo_count

        class _R:
            def scalar_one(self_inner):
                return count

        return _R()

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        self.flushed = True

    async def refresh(self, _obj):
        return None


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_content_type() -> None:
    from app.services.address_photos import upload_address_photo

    provider_id = uuid4()
    address = _address(provider_id)
    owner = _user(UserRole.OWNER.value, provider_id=provider_id)

    with pytest.raises(HTTPException) as exc:
        await upload_address_photo(
            db=_FakeSession(address),
            address_id=address.id,
            file_content=b"PDF data",
            original_filename="doc.pdf",
            content_type="application/pdf",
            user=owner,
        )
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_empty_payload() -> None:
    from app.services.address_photos import upload_address_photo

    provider_id = uuid4()
    address = _address(provider_id)
    owner = _user(UserRole.OWNER.value, provider_id=provider_id)

    with pytest.raises(HTTPException) as exc:
        await upload_address_photo(
            db=_FakeSession(address),
            address_id=address.id,
            file_content=b"",
            original_filename="empty.jpg",
            content_type="image/jpeg",
            user=owner,
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_upload_rejects_too_many_photos_per_address() -> None:
    from app.services.address_photos import (
        MAX_PHOTOS_PER_ADDRESS,
        upload_address_photo,
    )

    provider_id = uuid4()
    address = _address(provider_id)
    owner = _user(UserRole.OWNER.value, provider_id=provider_id)
    valid_jpeg = _make_png_bytes(640, 480)  # process_image конвертирует PNG -> JPEG

    with pytest.raises(HTTPException) as exc:
        await upload_address_photo(
            db=_FakeSession(address, photo_count=MAX_PHOTOS_PER_ADDRESS),
            address_id=address.id,
            file_content=valid_jpeg,
            original_filename="extra.png",
            content_type="image/png",
            user=owner,
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_upload_denies_owner_of_other_provider() -> None:
    from app.services.address_photos import upload_address_photo

    address = _address(uuid4())
    owner_of_other_provider = _user(UserRole.OWNER.value, provider_id=uuid4())
    valid_image = _make_png_bytes(320, 240)

    with pytest.raises(HTTPException) as exc:
        await upload_address_photo(
            db=_FakeSession(address),
            address_id=address.id,
            file_content=valid_image,
            original_filename="foreign.png",
            content_type="image/png",
            user=owner_of_other_provider,
        )
    assert exc.value.status_code == 403
