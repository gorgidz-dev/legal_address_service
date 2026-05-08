from __future__ import annotations

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
