"""Внутренняя оценка работы собственника — только для оператора."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class MetricRead(BaseModel):
    #: В единицах метрики: часы, доля 0..1.
    value: Optional[float] = None
    #: Нормированный балл 0..1. None — данных нет, метрика в итог не входит.
    score: Optional[float] = None
    sample: int


class ProviderRatingRead(BaseModel):
    provider_id: UUID
    provider_name: str
    response: MetricRead
    cards: MetricRead
    documents: MetricRead
    #: Итог 0..100. None — про собственника пока ничего не известно.
    score: Optional[int] = None
