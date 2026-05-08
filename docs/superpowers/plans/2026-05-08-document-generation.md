# Document Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MVP document generation that renders DOCX files from the existing templates and returns a ZIP package without requiring PDF conversion.

**Architecture:** Keep generation in focused services under `app/services/`: one module builds template context, one renders DOCX, and one assembles package files. Routers remain thin and coordinate database reads/writes.

**Tech Stack:** FastAPI, SQLAlchemy async, docxtpl, python-docx, pytils/petrovich-compatible formatting helpers, pytest.

---

### Task 1: Template Context And Local Storage

**Files:**
- Create: `app/services/document_context.py`
- Create: `app/services/storage.py`
- Test: `tests/test_document_context.py`

- [ ] Write tests for Russian date formatting, term end-date calculation, and context fields for initial-registration guarantee letters.
- [ ] Run `pytest tests/test_document_context.py -q` and confirm the tests fail because the service modules do not exist.
- [ ] Implement minimal context helpers and local storage path helpers.
- [ ] Run `pytest tests/test_document_context.py -q` and confirm the tests pass.

### Task 2: DOCX Rendering And ZIP Assembly

**Files:**
- Create: `app/services/document_renderer.py`
- Create: `app/services/document_package.py`
- Test: `tests/test_document_package.py`

- [ ] Write tests that render a DOCX from `templates/template_guarantee_initial.docx` and verify the output ZIP contains the DOCX and EGRN PDF.
- [ ] Run `pytest tests/test_document_package.py -q` and confirm the tests fail because the services do not exist.
- [ ] Implement rendering with `docxtpl.DocxTemplate` and ZIP assembly with Python `zipfile`.
- [ ] Run `pytest tests/test_document_package.py -q` and confirm the tests pass.

### Task 3: API Integration

**Files:**
- Modify: `app/routers/applications.py`
- Modify: `app/routers/egrn.py`
- Modify: `app/routers/templates.py`
- Test: `tests/test_document_api_smoke.py`

- [ ] Write an API smoke test or script that creates an application fixture and calls `generate_package`.
- [ ] Implement `issue_guarantee`, `generate_package`, and document listing using existing ORM models.
- [ ] Keep PDF optional: generated records may have `pdf_url = null`.
- [ ] Verify with pytest and one live local API call against PostgreSQL.

### Scope Notes

This MVP stores generated files under local `storage/` paths and exposes those paths as URLs/identifiers. S3/MinIO and LibreOffice PDF conversion remain later steps and should not block DOCX generation.
