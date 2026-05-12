from __future__ import annotations

import asyncio
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.stored_file import StoredFile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = PROJECT_ROOT / "storage"
GENERATED_ROOT = STORAGE_ROOT / "generated"
EGRN_ROOT = STORAGE_ROOT / "egrn"
TEMPLATE_ROOT = STORAGE_ROOT / "templates"
CLOUD_LOCAL_ROOT = STORAGE_ROOT / "cloud"


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


@dataclass(frozen=True)
class StoredObject:
    backend: str
    key: str
    public_url: str | None = None


class LocalObjectStorage:
    backend = "local"

    def __init__(self, root: Path = CLOUD_LOCAL_ROOT) -> None:
        self.root = root

    def _resolve_key(self, key: str) -> Path:
        if key.startswith("/") or ".." in Path(key).parts:
            raise ValueError("Некорректный ключ файла")
        candidate = (self.root / key).resolve()
        root = self.root.resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("Некорректный ключ файла")
        return candidate

    def put_bytes(self, *, key: str, content: bytes, content_type: str) -> StoredObject:
        path = self._resolve_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return StoredObject(backend=self.backend, key=key)

    def read_bytes(self, key: str) -> bytes:
        return self._resolve_key(key).read_bytes()

    def path_for(self, key: str) -> Path:
        path = self._resolve_key(key)
        if not path.is_file():
            raise FileNotFoundError(f"Файл не найден: {key}")
        return path


class S3ObjectStorage:
    backend = "s3"

    def __init__(self) -> None:
        if not settings.s3_access_key or not settings.s3_secret_key or not settings.s3_bucket:
            raise RuntimeError("Для STORAGE_BACKEND=s3 нужны S3_ACCESS_KEY, S3_SECRET_KEY и S3_BUCKET")
        import boto3

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint or None,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )

    def put_bytes(self, *, key: str, content: bytes, content_type: str) -> StoredObject:
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        public_url = None
        if settings.s3_endpoint:
            public_url = f"{settings.s3_endpoint.rstrip('/')}/{self.bucket}/{key}"
        return StoredObject(backend=self.backend, key=key, public_url=public_url)

    def read_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()


def get_object_storage() -> LocalObjectStorage | S3ObjectStorage:
    if settings.storage_backend.lower() == "s3":
        return S3ObjectStorage()
    return LocalObjectStorage()


def safe_storage_filename(original_filename: str) -> str:
    name = Path(original_filename or "file").name or "file"
    name = name.replace("ё", "е").replace("Ё", "Е")
    name = re.sub(r"[^0-9A-Za-zА-Яа-я._-]", "_", name)
    name = name.strip("._")
    return name or "file"


def object_storage_key(
    *,
    kind: str,
    original_filename: str,
    content_hash: str,
    client_id: UUID | str | None = None,
    application_id: UUID | str | None = None,
) -> str:
    parts: list[str] = []
    if client_id is not None:
        parts.extend(["clients", str(client_id)])
    if application_id is not None:
        parts.extend(["applications", str(application_id)])
    if not parts:
        parts.append("unassigned")
    parts.extend([kind, content_hash[:16], safe_storage_filename(original_filename)])
    return "/".join(parts)


async def create_stored_file_record(
    *,
    db: AsyncSession,
    content: bytes,
    kind: str,
    original_filename: str,
    content_type: str,
    client_id: UUID | str | None = None,
    application_id: UUID | str | None = None,
    uploaded_by: UUID | str | None = None,
) -> StoredFile:
    content_hash = hashlib.sha256(content).hexdigest()
    key = object_storage_key(
        kind=kind,
        original_filename=original_filename,
        content_hash=content_hash,
        client_id=client_id,
        application_id=application_id,
    )
    stored_object = await asyncio.to_thread(
        get_object_storage().put_bytes,
        key=key,
        content=content,
        content_type=content_type,
    )
    file_record = StoredFile(
        client_id=client_id,
        application_id=application_id,
        kind=kind,
        original_filename=original_filename,
        content_type=content_type,
        size_bytes=len(content),
        sha256=content_hash,
        storage_backend=stored_object.backend,
        storage_key=stored_object.key,
        public_url=stored_object.public_url,
        created_at=datetime.now(timezone.utc),
        uploaded_by=uploaded_by,
    )
    db.add(file_record)
    await db.flush()
    return file_record


def read_stored_file(file_record: StoredFile) -> bytes:
    if file_record.storage_backend == "local":
        return LocalObjectStorage().read_bytes(file_record.storage_key)
    if file_record.storage_backend == "s3":
        return S3ObjectStorage().read_bytes(file_record.storage_key)
    raise ValueError(f"Неизвестный backend файла: {file_record.storage_backend}")


async def read_stored_file_async(file_record: StoredFile) -> bytes:
    """Off-load disk/S3 reads to a worker thread."""
    return await asyncio.to_thread(read_stored_file, file_record)


def local_stored_file_path(file_record: StoredFile) -> Path | None:
    if file_record.storage_backend != "local":
        return None
    return LocalObjectStorage().path_for(file_record.storage_key)
