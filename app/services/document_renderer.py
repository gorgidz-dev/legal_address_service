from __future__ import annotations

import asyncio
from io import BytesIO
from pathlib import Path
from typing import Any

from docxtpl import DocxTemplate


def render_docx(
    *,
    template_path: Path,
    output_path: Path,
    context: dict[str, Any],
) -> Path:
    if not template_path.exists():
        raise FileNotFoundError(f"Шаблон не найден: {template_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    template = DocxTemplate(str(template_path))
    template.render(context)
    template.save(str(output_path))
    return output_path


def render_docx_bytes(*, template_bytes: bytes, context: dict[str, Any]) -> bytes:
    template = DocxTemplate(BytesIO(template_bytes))
    template.render(context)
    output = BytesIO()
    template.save(output)
    return output.getvalue()


async def render_docx_async(
    *,
    template_path: Path,
    output_path: Path,
    context: dict[str, Any],
) -> Path:
    """Run DOCX rendering in a thread — docxtpl is CPU-bound and blocking."""
    return await asyncio.to_thread(
        render_docx,
        template_path=template_path,
        output_path=output_path,
        context=context,
    )


async def render_docx_bytes_async(*, template_bytes: bytes, context: dict[str, Any]) -> bytes:
    return await asyncio.to_thread(
        render_docx_bytes, template_bytes=template_bytes, context=context
    )
