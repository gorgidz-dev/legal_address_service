"""Разбор PDF-расписки ИФНС о приёме документов (статус-трекер, этап 6).

Расписку клиент получает от ИФНС на почту PDF-файлом (так в 99% случаев —
решение владельца 13.10.2026), и в нём есть текст: из него берём дату
предстоящей регистрации, название компании, а для смены адреса — ИНН/ОГРН.
Клиент проверяет найденное и может поправить дату; файл без текста (скан,
фото) не принимаем — просим загрузить PDF из письма.

Разбор — по типовым формулировкам расписки, без привязки к вёрстке: формы и
шаблоны писем ФНС меняются. Что не нашлось — остаётся пустым, это не ошибка.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from io import BytesIO
from typing import Any, Optional

#: Сколько страниц читать: расписка — 1–2 страницы, дальше незачем.
MAX_PAGES = 5
#: Пределы разбора. PDF в 16 КБ может распаковаться в десятки мегабайт
#: операторов, и pypdf будет разбирать их минутами. У настоящей расписки —
#: ~8 КБ содержимого и ~1 тыс. операторов на страницу, так что запас стократный.
MAX_CONTENT_BYTES = 2 * 1024 * 1024
MAX_OPERATORS = 200_000
MAX_TEXT_CHARS = 50_000
#: Глубина вложенных форм (XObject), которую считаем в размер содержимого.
_MAX_FORM_DEPTH = 4

_MONTHS = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6,
    "июля": 7, "августа": 8, "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_DATE = re.compile(
    r"(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})"
    r"|(?P<dw>\d{1,2})\s+(?P<mw>" + "|".join(_MONTHS) + r")\s+(?P<yw>\d{4})",
    re.IGNORECASE,
)
#: После этих слов идёт дата, когда регистрация будет готова.
_READY_WORDS = re.compile(r"готов|выдач|не\s+позднее|срок", re.IGNORECASE)
#: После этих — дата, когда ИФНС получила документы.
_RECEIVED_WORDS = re.compile(r"получени|получен|поступ|представлен|приня", re.IGNORECASE)
_RECEIPT_WORDS = re.compile(r"расписк|получении\s+документов|регистрирующ", re.IGNORECASE)
#: Название — до последней кавычки в строке: вложенные кавычки в ЕГРЮЛ обычны
#: (ООО "ТОРГОВЫЙ ДОМ "РОМАШКА""), и первая закрывающая обрезала бы его.
_QUOTED_NAME = re.compile(
    r"((?:ОБЩЕСТВ[А-Я]*\s+С\s+ОГРАНИЧЕННОЙ\s+ОТВЕТСТВЕННОСТЬЮ|АКЦИОНЕРН[А-Я]*\s+ОБЩЕСТВ[А-Я]*|"
    r"ООО|АО|ПАО|НАО)\s*[«\"“„][^\n]{0,150}[»\"”“])",
    re.IGNORECASE,
)
_NAME_LINE = re.compile(r"наименование[^:\n]{0,60}[:\-]\s*([^\n]{2,200})", re.IGNORECASE)
_INN = re.compile(r"ИНН\D{0,15}(\d{10})(?!\d)")
_OGRN = re.compile(r"ОГРН\D{0,15}(\d{13})(?!\d)")
#: Дата получения документов в бланке расписки — «клетками»:
#: «29» число «апреля» месяц прописью «2026» год.
_BOX_DATE = re.compile(
    r"«\s*(\d{1,2})\s*»\s*число\s*«\s*([а-яё]+)\s*»\s*месяц[^«]{0,40}«\s*(\d{4})\s*»",
    re.IGNORECASE,
)
_IFNS = re.compile(
    r"((?:Межрайонная\s+)?[Ии]нспекция\s+Федеральной\s+налоговой\s+службы[^\n(]{0,80})"
)
_NUMBER = re.compile(r"(?:вход[а-я]*\s+номер|вх\.?\s*№|№)\s*[:\-]?\s*([0-9]{3,}[0-9A-ZА-Я\-/]*)", re.IGNORECASE)
#: Код формы заявления: Р11001 — создание, Р13014 — изменения (в т.ч. адреса).
_FORM = re.compile(r"(?<![0-9A-Za-zА-Яа-я])[РP]\s?1\d{4}(?!\d)")


@dataclass
class ReceiptData:
    has_text: bool
    looks_like_receipt: bool
    expected_on: Optional[date] = None
    submitted_on: Optional[date] = None
    company_name: Optional[str] = None
    inn: Optional[str] = None
    ogrn: Optional[str] = None
    number: Optional[str] = None
    form: Optional[str] = None
    ifns: Optional[str] = None

    def as_json(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("expected_on", "submitted_on"):
            data[key] = data[key].isoformat() if data[key] else None
        return data


class _TooHeavy(Exception):
    """PDF слишком тяжёл для расписки — разбирать не будем."""


def _content_size(stream: Any) -> int:
    try:
        return len(stream.get_data()) if stream is not None else 0
    except Exception:  # noqa: BLE001 — битый поток: pypdf его всё равно пропустит
        return 0


def _forms_size(resources: Any, depth: int = 0) -> int:
    """Распакованный размер форм (XObject), которые рисует страница или форма:
    pypdf разбирает их вместе со страницей, и тяжесть можно спрятать туда."""
    if depth >= _MAX_FORM_DEPTH or resources is None:
        return 0
    try:
        xobjects = resources.get_object().get("/XObject")
        items = list(xobjects.get_object().values()) if xobjects is not None else []
    except Exception:  # noqa: BLE001
        return 0
    total = 0
    for item in items:
        form = item.get_object()
        if form.get("/Subtype") != "/Form":
            continue
        total += _content_size(form) + _forms_size(form.get("/Resources"), depth + 1)
        if total > MAX_CONTENT_BYTES:
            break
    return total


def extract_text(content: bytes) -> str:
    """Текст первых страниц PDF. Пустая строка — не PDF, PDF без текста (скан)
    или файл, разбор которого вышел бы за пределы (MAX_CONTENT_BYTES, MAX_OPERATORS).

    Синхронная и может занять до секунды — вызывать из потока, не из event loop.
    """
    from pypdf import PdfReader  # тяжёлый импорт — только когда правда нужен

    operators = 0

    def count_operator(*_: Any) -> None:
        nonlocal operators
        operators += 1
        if operators > MAX_OPERATORS:
            raise _TooHeavy

    try:
        reader = PdfReader(BytesIO(content))
        budget = MAX_CONTENT_BYTES
        texts = []
        for page in reader.pages[:MAX_PAGES]:
            # Размер — до разбора: сам разбор потока операторов и есть дорогая часть.
            budget -= _content_size(page.get_contents()) + _forms_size(page.get("/Resources"))
            if budget < 0:
                raise _TooHeavy
            texts.append(page.extract_text(visitor_operand_before=count_operator) or "")
        return "\n".join(texts)[:MAX_TEXT_CHARS]
    except Exception:  # noqa: BLE001 — битый/зашифрованный/не PDF/слишком тяжёлый: разбирать нечего
        return ""


def _normalize(text: str) -> str:
    text = text.replace("\xa0", " ").replace(" ", " ")
    return re.sub(r"[ \t]+", " ", text)


def _to_date(match: re.Match) -> Optional[date]:
    try:
        if match.group("d"):
            return date(int(match.group("y")), int(match.group("m")), int(match.group("d")))
        return date(int(match.group("yw")), _MONTHS[match.group("mw").lower()], int(match.group("dw")))
    except (ValueError, KeyError):
        return None


def _dates(text: str) -> list[tuple[int, date]]:
    found = []
    for match in _DATE.finditer(text):
        value = _to_date(match)
        if value is not None:
            found.append((match.start(), value))
    return found


def _date_after(text: str, words: re.Pattern, dates: list[tuple[int, date]], window: int = 250) -> Optional[date]:
    """Первая дата не дальше `window` символов после одного из слов."""
    for word in words.finditer(text):
        for position, value in dates:
            if word.end() <= position <= word.end() + window:
                return value
    return None


def _clean_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" .,;:")


def parse_receipt_text(text: str) -> ReceiptData:
    text = _normalize(text)
    if not text.strip():
        return ReceiptData(has_text=False, looks_like_receipt=False)
    dates = _dates(text)
    box = _BOX_DATE.search(text)
    submitted = None
    if box:
        try:
            submitted = date(int(box.group(3)), _MONTHS[box.group(2).lower()], int(box.group(1)))
        except (ValueError, KeyError):
            submitted = None
    if submitted is None:
        submitted = _date_after(text, _RECEIVED_WORDS, dates)
    # В бланке ФНС: «Дата выдачи регистрирующим органом документов, предусмотренных
    # законодательством о государственной регистрации … М.П. 08.05.2026».
    expected = _date_after(text, _READY_WORDS, dates)
    if expected is None and dates and (len(dates) >= 2 or submitted is not None):
        # Подписей не нашли — дата готовности всегда позже даты получения.
        latest = max(value for _, value in dates)
        if submitted is None or latest > submitted:
            expected = latest
    if expected is not None and submitted is not None and expected < submitted:
        expected = None  # перепутали поля — пусть клиент введёт сам

    name = None
    quoted = _QUOTED_NAME.search(text)
    if quoted:
        name = _clean_name(quoted.group(1))
    else:
        line = _NAME_LINE.search(text)
        if line:
            name = _clean_name(line.group(1))[:200] or None

    inn = _INN.search(text)
    ogrn = _OGRN.search(text)
    number = _NUMBER.search(text)
    form = _FORM.search(text)
    ifns = _IFNS.search(text)
    ifns_name = None
    if ifns:
        # В PDF подпись поля склеивается с названием: «… по г. Москвеналоговый орган».
        ifns_name = re.sub(r"\s*налоговый\s+орган\s*$", "", ifns.group(1), flags=re.IGNORECASE).strip() or None
    return ReceiptData(
        has_text=True,
        looks_like_receipt=bool(_RECEIPT_WORDS.search(text)),
        expected_on=expected,
        submitted_on=submitted,
        company_name=name,
        inn=inn.group(1) if inn else None,
        ogrn=ogrn.group(1) if ogrn else None,
        number=number.group(1) if number else None,
        form=re.sub(r"\s", "", form.group(0)).replace("P", "Р") if form else None,
        ifns=ifns_name,
    )


def parse_receipt_pdf(content: bytes) -> ReceiptData:
    return parse_receipt_text(extract_text(content))
