"""Разбор расписки ИФНС. Текст — обезличенная копия настоящего бланка ФНС
(образец владельца 13.10.2026): структура и переносы строк те же, данные
выдуманы (ОГРН — публичный, ПАО Сбербанк). Сам файл в репозиторий не кладём —
в нём персональные данные, а репозиторий публичный."""
from __future__ import annotations

from datetime import date

import pytest

from app.services.ifns_receipt import extract_text, parse_receipt_text

FNS_BLANK = """Расписка
в получении документов, представленных при государственной регистрации
юридического лица
Настоящим удостоверяется, что в отношении
ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРИМЕР"
(полное наименование юридического лица)
Межрайонная инспекция Федеральной налоговой службы № 46 по г. Москвеналоговый орган
(наименование налогового органа)
« 29 »
число
«  апреля  »
месяц прописью
« 2026 »
год
вх № 100000А получил нижеследующие документы
ОГРН 1027700132195
Наименование документа Имя файла с документом
1 2 3
№
1 Р13014 Заявление об изменении учр.документа и/или иных сведений о ЮЛ ZayavUL_0000.pdf
2 Решение об изменении места нахождения ЮЛ PrilozhDokum_0001.pdf
Указанные документы направлены по каналам связи. Заявителем является ИВАНОВА ИРИНА
ИВАНОВНА
Расписка сформирована с учетом сведений, содержащихся в заявке с документами, поданными в
электронном виде через сайт Федеральной налоговой службы. Номер заявки - U000000000000000
Дата выдачи регистрирующим органом документов,
предусмотренных законодательством о государственной
регистрации
М.П.
08.05.2026"""


def test_real_fns_blank_is_parsed() -> None:
    data = parse_receipt_text(FNS_BLANK)
    assert data.has_text and data.looks_like_receipt
    assert data.submitted_on == date(2026, 4, 29)  # «клетками»: «29» «апреля» «2026»
    assert data.expected_on == date(2026, 5, 8)  # далеко после «Дата выдачи …», после «М.П.»
    assert data.company_name == 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ПРИМЕР"'
    assert data.ogrn == "1027700132195" and data.inn is None
    assert data.number == "100000А"
    assert data.form == "Р13014"
    assert data.ifns == "Межрайонная инспекция Федеральной налоговой службы № 46 по г. Москве"


def test_applicant_name_is_not_kept() -> None:
    assert "ИВАНОВА" not in str(parse_receipt_text(FNS_BLANK).as_json())


def test_new_company_blank_with_inn_and_written_date() -> None:
    data = parse_receipt_text(
        "Расписка в получении документов\nООО «Новая», ИНН 7707083893\n"
        "Документы получены 13.10.2026. Документы будут готовы к выдаче не позднее 19 октября 2026 г."
    )
    assert (data.submitted_on, data.expected_on) == (date(2026, 10, 13), date(2026, 10, 19))
    assert data.company_name == "ООО «Новая»" and data.inn == "7707083893"


def test_date_before_submission_is_not_trusted() -> None:
    data = parse_receipt_text("Расписка\nДата получения 20.10.2026\nДата выдачи 01.10.2026")
    assert data.expected_on is None


def test_scan_or_garbage_has_no_text() -> None:
    assert parse_receipt_text("   ").has_text is False
    assert extract_text(b"not a pdf at all") == ""


def test_nested_quotes_keep_whole_company_name() -> None:
    data = parse_receipt_text(
        'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТОРГОВЫЙ ДОМ "РОМАШКА""\n'
        "(полное наименование юридического лица)"
    )
    assert data.company_name == 'ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "ТОРГОВЫЙ ДОМ "РОМАШКА""'
    assert parse_receipt_text("ООО «ТД «Ромашка»»").company_name == "ООО «ТД «Ромашка»»"


def _heavy_pdf(*, via_form: bool) -> bytes:
    """16 КБ PDF, который распаковывается в ~10 МБ операторов `(a) Tj`."""
    import zlib

    body = b"BT /F1 12 Tf " + b"(a) Tj " * 1_500_000 + b"ET"
    packed = zlib.compress(body, 9)
    font = b"/Font << /F1 << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> >>"
    heavy = b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(packed) + packed + b"\nendstream"
    if via_form:
        form = b"<< /Type /XObject /Subtype /Form /BBox [0 0 10 10] /Resources << " + font + b" >> /Length"
        heavy = heavy.replace(b"<< /Length", form, 1)
        draw = b"<< /Length 6 >>\nstream\n/X1 Do\nendstream"
        page = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << " + font + (
            b" /XObject << /X1 3 0 R >> >> /Contents 4 0 R >>"
        )
    else:
        draw = b"<< /Length 0 >>\nstream\n\nendstream"
        page = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << " + font + b" >> /Contents 3 0 R >>"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [5 0 R] /Count 1 >>",
        heavy,
        draw,
        page,
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objects) + 1, xref)
    return bytes(out)


@pytest.mark.parametrize("via_form", [False, True])
def test_heavy_pdf_is_refused_quickly(via_form: bool) -> None:
    """Маленький файл не должен занимать воркер минутами (до пределов — 100+ с)."""
    import time

    content = _heavy_pdf(via_form=via_form)
    assert len(content) < 50_000
    started = time.monotonic()
    assert extract_text(content) == ""
    assert time.monotonic() - started < 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "accepted"),
    [
        ("Счёт на оплату № 157 от 01.10.2026\nПолучено 01.10.2026", False),
        ("Межрайонная инспекция Федеральной налоговой службы № 46 по г. Москве\nвх № 100000А", True),
        (FNS_BLANK, True),
    ],
)
async def test_only_receipt_like_pdf_is_accepted(monkeypatch, text: str, accepted: bool) -> None:
    from fastapi import HTTPException

    from app.services import application_documents

    monkeypatch.setattr(application_documents, "parse_receipt_pdf", lambda _content: parse_receipt_text(text))
    reading = application_documents.read_ifns_receipt(b"%PDF-1.4", "raspiska.pdf")
    if accepted:
        assert (await reading).has_text
    else:
        with pytest.raises(HTTPException, match="не похоже на расписку"):
            await reading
