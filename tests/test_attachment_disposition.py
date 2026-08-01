"""Имя файла в заголовке переживает кириллицу.

HTTP-заголовки кодируются latin-1, поэтому `filename="Расписка.pdf"` роняет
ответ на кодировании. На проде так падало скачивание ЛЮБОГО файла с русским
именем — а русские имена здесь норма: расписки, договоры, выписки ЕГРН.

Локально это не воспроизводилось: при STORAGE_BACKEND=local отдаёт
FileResponse, который экранирует имя сам. Ломалась только ветка S3, то есть
ровно прод.
"""
from __future__ import annotations

import pytest

from app.services.storage import attachment_disposition

ROUTERS_WITH_DOWNLOADS = (
    "app/routers/address_chats.py",
    "app/routers/address_documents.py",
    "app/routers/application_documents.py",
    "app/routers/clients.py",
    "app/routers/payments.py",
)


def test_ascii_name_stays_readable():
    assert attachment_disposition("contract.pdf") == 'attachment; filename="contract.pdf"'


def test_cyrillic_name_is_percent_encoded():
    header = attachment_disposition("Расписка.pdf")
    assert header.startswith("attachment; filename*=utf-8''")
    assert "%D0%A0" in header  # «Р»


@pytest.mark.parametrize(
    "filename",
    [
        "Расписка о приёме документов.pdf",
        "Договор №12 от 01.08.2026.docx",
        "Выписка ЕГРН — Тверская, 7.pdf",
        "naïve café.txt",
        "квитанция 100%.pdf",
    ],
)
def test_header_is_encodable_as_latin1(filename):
    """Главная проверка: заголовок вообще уходит в сеть."""
    attachment_disposition(filename).encode("latin-1")


def test_no_router_builds_the_header_by_hand():
    """Ручная f-строка с именем файла — это тот же баг, заведённый заново."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    offenders = []
    for relative in ROUTERS_WITH_DOWNLOADS:
        source = (root / relative).read_text(encoding="utf-8")
        if "attachment; filename=" in source.replace(
            "attachment; filename*=utf-8''", ""
        ):
            offenders.append(relative)
    assert offenders == [], (
        f"заголовок собирается вручную в {offenders} — используйте "
        "storage.attachment_disposition()"
    )
