"""Разбор расписки ИФНС. Текст — обезличенная копия настоящего бланка ФНС
(образец владельца 13.10.2026): структура и переносы строк те же, данные
выдуманы (ОГРН — публичный, ПАО Сбербанк). Сам файл в репозиторий не кладём —
в нём персональные данные, а репозиторий публичный."""
from __future__ import annotations

from datetime import date

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
        "Расписка в получении документов\\nООО «Новая», ИНН 7707083893\\n"
        "Документы получены 13.10.2026. Документы будут готовы к выдаче не позднее 19 октября 2026 г."
    )
    assert (data.submitted_on, data.expected_on) == (date(2026, 10, 13), date(2026, 10, 19))
    assert data.company_name == "ООО «Новая»" and data.inn == "7707083893"


def test_date_before_submission_is_not_trusted() -> None:
    data = parse_receipt_text("Расписка\\nДата получения 20.10.2026\\nДата выдачи 01.10.2026")
    assert data.expected_on is None


def test_scan_or_garbage_has_no_text() -> None:
    assert parse_receipt_text("   ").has_text is False
    assert extract_text(b"not a pdf at all") == ""
