from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

from docx import Document

from app.services.document_package import create_package_zip
from app.services.document_renderer import render_docx


def test_render_docx_replaces_initial_guarantee_variables(tmp_path: Path) -> None:
    template_path = Path("templates/template_guarantee_initial.docx")
    output_path = tmp_path / "guarantee.docx"

    render_docx(
        template_path=template_path,
        output_path=output_path,
        context={
            "fns_number": 46,
            "fns_city": "Москве",
            "provider_full_name": "Индивидуальный предприниматель Иванов Иван Иванович",
            "provider_inn": "503809113832",
            "provider_ogrn": "304770001734651",
            "provider_legal_address": "123456, г. Москва, ул. Тверская, д. 1",
            "provider_phone": "+74951234567",
            "guarantee_number": "ГП-2026-0001",
            "guarantee_date_ru": "«08» мая 2026 г.",
            "address_full": "123456, г. Москва, ул. Тверская, д. 1, помещение № 5",
            "address_cadastral_number": "77:01:0001001:1234",
            "client_planned_name": "Альфа",
            "ownership_doc_short": "Выписки из ЕГРН",
            "ownership_doc_pages": 3,
            "provider_signatory_initials": "Иванов И. И.",
        },
    )

    doc_text = "\n".join(p.text for p in Document(output_path).paragraphs)
    assert "{{" not in doc_text
    assert "ГП-2026-0001" in doc_text
    assert "Альфа" in doc_text


def test_create_package_zip_includes_docx_and_egrn_pdf(tmp_path: Path) -> None:
    docx_path = tmp_path / "guarantee.docx"
    pdf_path = tmp_path / "egrn.pdf"
    zip_path = tmp_path / "package.zip"

    docx_path.write_bytes(b"fake-docx")
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    create_package_zip(
        zip_path=zip_path,
        entries=[
            (docx_path, "01_гарантийное_письмо.docx"),
            (pdf_path, "02_выписка_егрн.pdf"),
        ],
    )

    with ZipFile(zip_path) as zf:
        assert zf.namelist() == [
            "01_гарантийное_письмо.docx",
            "02_выписка_егрн.pdf",
        ]
        assert zf.read("02_выписка_егрн.pdf") == b"%PDF-1.4 fake"
