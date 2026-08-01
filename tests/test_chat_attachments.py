"""Вложения в переписке: что принимаем, что отвергаем, что можно скачать.

Главное здесь — не удобство, а два отказа: файл, который браузер мог бы
выполнить как страницу с нашего домена, и вложение из чужой ветки.
"""
from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.services.chat_attachments import (
    MAX_ATTACHMENT_BYTES,
    MAX_ATTACHMENTS_PER_MESSAGE,
    content_type_for,
    ensure_message_has_content,
    ensure_within_limits,
    load_attachment,
)


# --- тип файла ---


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Договор.pdf", "application/pdf"),
        ("скан.JPG", "image/jpeg"),
        ("выписка.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("подпись.p7s", "application/pkcs7-signature"),
        ("архив.zip", "application/zip"),
    ],
)
def test_allowed_types_resolve_by_extension(filename, expected):
    assert content_type_for(filename) == expected


@pytest.mark.parametrize(
    "filename",
    ["письмо.html", "картинка.svg", "setup.exe", "script.js", "макрос.docm", "без_расширения"],
)
def test_dangerous_and_unknown_files_are_rejected(filename):
    """HTML и SVG выполнились бы в контексте нашего домена — их не принимаем."""
    with pytest.raises(HTTPException) as exc:
        content_type_for(filename)
    assert exc.value.status_code == 422


def test_type_comes_from_extension_not_from_the_uploader():
    """`письмо.html` нельзя протащить, назвав его картинкой в content-type.

    Тип мы вычисляем сами: заголовок присылает загружающая сторона, и доверять
    ему — значит отдавать обратно то, что она объявит.
    """
    with pytest.raises(HTTPException):
        content_type_for("письмо.html")
    assert content_type_for("письмо.pdf") == "application/pdf"


# --- размер ---


def test_empty_file_is_rejected():
    with pytest.raises(HTTPException) as exc:
        ensure_within_limits(content=b"", original_filename="пусто.pdf")
    assert exc.value.status_code == 422


def test_file_over_the_limit_is_rejected():
    with pytest.raises(HTTPException) as exc:
        ensure_within_limits(
            content=b"x" * (MAX_ATTACHMENT_BYTES + 1), original_filename="скан.pdf"
        )
    assert exc.value.status_code == 413


def test_file_exactly_at_the_limit_passes():
    ensure_within_limits(content=b"x" * MAX_ATTACHMENT_BYTES, original_filename="скан.pdf")


# --- содержимое сообщения ---


def test_message_without_text_and_files_is_rejected():
    with pytest.raises(HTTPException) as exc:
        ensure_message_has_content(body="   ", attachment_count=0)
    assert exc.value.status_code == 422


def test_file_without_text_is_allowed():
    """«Вот договор» без единого слова — нормальное сообщение."""
    ensure_message_has_content(body="", attachment_count=1)


def test_text_without_files_is_allowed():
    ensure_message_has_content(body="Здравствуйте", attachment_count=0)


def test_too_many_files_are_rejected():
    with pytest.raises(HTTPException) as exc:
        ensure_message_has_content(body="", attachment_count=MAX_ATTACHMENTS_PER_MESSAGE + 1)
    assert exc.value.status_code == 422


# --- скачивание ---


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, row):
        self._row = row

    async def execute(self, _stmt):
        return _Result(self._row)


CHAT = uuid4()
OTHER_CHAT = uuid4()


@pytest.mark.asyncio
async def test_attachment_of_this_thread_is_returned():
    file_record = SimpleNamespace(id=uuid4(), original_filename="Договор.pdf")
    row = (
        SimpleNamespace(id=uuid4()),
        file_record,
        SimpleNamespace(chat_id=CHAT),
    )
    result = await load_attachment(
        db=_FakeSession(row), chat_id=CHAT, attachment_id=row[0].id
    )
    assert result is file_record


@pytest.mark.asyncio
async def test_attachment_from_another_thread_is_not_found():
    """Участник одной переписки не должен вытащить файл из чужой по id."""
    row = (
        SimpleNamespace(id=uuid4()),
        SimpleNamespace(id=uuid4(), original_filename="Чужой.pdf"),
        SimpleNamespace(chat_id=OTHER_CHAT),
    )
    with pytest.raises(HTTPException) as exc:
        await load_attachment(db=_FakeSession(row), chat_id=CHAT, attachment_id=row[0].id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_missing_attachment_is_not_found():
    with pytest.raises(HTTPException) as exc:
        await load_attachment(db=_FakeSession(None), chat_id=CHAT, attachment_id=uuid4())
    assert exc.value.status_code == 404
