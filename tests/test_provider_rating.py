"""Внутренняя оценка работы собственника.

Проверяется главным образом то, что оценка не врёт в двух опасных местах:
собственник без данных не получает ноль, а возврат документов не путается с
запросом уточнений у клиента.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.provider_rating import (
    BAD_RESPONSE_HOURS,
    GOOD_RESPONSE_HOURS,
    _first_response_hours,
    build_rating,
    card_completeness,
    response_score,
)

PROVIDER = uuid4()
CLIENT = uuid4()
OWNER = uuid4()
T0 = datetime(2026, 7, 30, 9, tzinfo=timezone.utc)


def _address(**kwargs):
    defaults = dict(description="Офис", amenities=["metro"], price_11m=30000, fns_number=46)
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _message(author, hours):
    return SimpleNamespace(author_user_id=author, created_at=T0 + timedelta(hours=hours))


# --- скорость ответа ---


def test_fast_answer_gets_full_score():
    assert response_score(GOOD_RESPONSE_HOURS) == 1.0
    assert response_score(0.5) == 1.0


def test_very_slow_answer_gets_zero():
    assert response_score(BAD_RESPONSE_HOURS) == 0.0
    assert response_score(500) == 0.0


def test_score_decreases_monotonically():
    scores = [response_score(h) for h in (4, 12, 24, 36, 48)]
    assert scores == sorted(scores, reverse=True)


def test_burst_of_client_messages_counts_as_one_wait():
    """Клиент написал трижды, собственник ответил один раз — это одно ожидание."""
    messages = [
        _message(CLIENT, 0),
        _message(CLIENT, 1),
        _message(CLIENT, 2),
        _message(OWNER, 5),
    ]
    assert _first_response_hours(messages, {OWNER}) == [5.0]


def test_owner_messages_without_question_are_not_waits():
    messages = [_message(OWNER, 0), _message(OWNER, 1)]
    assert _first_response_hours(messages, {OWNER}) == []


def test_unanswered_question_is_not_counted_as_instant():
    """Без ответа ожидание не закрыто — в статистику оно не попадает вовсе."""
    messages = [_message(CLIENT, 0)]
    assert _first_response_hours(messages, {OWNER}) == []


# --- заполненность карточки ---


def test_full_card_is_one():
    assert card_completeness(_address()) == 1.0


def test_empty_card_is_zero():
    assert card_completeness(
        _address(description="", amenities=[], price_11m=None, fns_number=None)
    ) == 0.0


def test_blank_description_does_not_count():
    """Пробелы — это не заполненное описание."""
    assert card_completeness(_address(description="   ")) == 0.75


# --- итоговый балл ---


def _rating(**kwargs):
    defaults = dict(
        provider_id=PROVIDER,
        response_waits=[],
        addresses=[],
        documents_total=0,
        documents_returned=0,
    )
    defaults.update(kwargs)
    return build_rating(**defaults)


def test_provider_without_any_data_has_no_score():
    """Новый собственник не должен получать двойку за то, что ему не писали."""
    rating = _rating()
    assert rating.score is None
    assert rating.response.sample == 0


def test_metric_without_data_does_not_drag_the_score_down():
    """Один заполненный показатель — итог по нему, а не среднее с нулями."""
    rating = _rating(addresses=[_address()])
    assert rating.score == 100


def test_returned_documents_lower_the_score():
    good = _rating(documents_total=10, documents_returned=0).documents.score
    bad = _rating(documents_total=10, documents_returned=5).documents.score
    assert good == 1.0
    assert bad == 0.5


def test_median_is_used_not_average():
    """Один отпуск на две недели не должен утаскивать оценку."""
    waits = [1.0, 1.0, 1.0, 1.0, 336.0]
    rating = _rating(response_waits=waits)
    assert rating.response.value == 1.0
    assert rating.response.score == 1.0


def test_score_is_average_of_available_metrics():
    rating = _rating(
        response_waits=[GOOD_RESPONSE_HOURS],
        addresses=[_address(description="", amenities=[], price_11m=None, fns_number=None)],
    )
    # 1.0 и 0.0 по двум метрикам → 50.
    assert rating.score == 50


@pytest.mark.parametrize("returned", [0, 3, 10])
def test_score_never_leaves_zero_hundred(returned):
    rating = _rating(documents_total=10, documents_returned=returned)
    assert 0 <= (rating.score or 0) <= 100
