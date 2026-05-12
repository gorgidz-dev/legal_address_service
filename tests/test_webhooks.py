from __future__ import annotations

import hmac
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from app.models.webhook_delivery import WebhookDelivery
from app.models.webhook_subscription import WebhookSubscription
from app.services.webhooks import (
    DELIVERY_ID_HEADER,
    INITIAL_BACKOFF,
    MAX_ATTEMPTS,
    MAX_BACKOFF,
    SIGNATURE_HEADER,
    compute_backoff,
    deliver_pending,
    dispatch_event,
    sign_payload,
    verify_signature,
)


def _now():
    return datetime.now(timezone.utc)


# ---- HMAC signature ---------------------------------------------------------


def test_sign_payload_uses_sha256_hmac_with_prefix() -> None:
    body = b'{"event": "x"}'
    sig = sign_payload("super-secret", body)
    assert sig.startswith("sha256=")
    expected = "sha256=" + hmac.new(b"super-secret", body, "sha256").hexdigest()
    assert sig == expected


def test_verify_signature_matches_signed_value() -> None:
    body = b"hello"
    sig = sign_payload("topsecret", body)
    assert verify_signature("topsecret", body, sig)
    assert not verify_signature("topsecret", body, "sha256=000")
    assert not verify_signature("wrong-secret", body, sig)
    assert not verify_signature("topsecret", body, None)


# ---- Backoff curve ----------------------------------------------------------


def test_compute_backoff_doubles_then_caps() -> None:
    assert compute_backoff(1) == INITIAL_BACKOFF
    assert compute_backoff(2) == INITIAL_BACKOFF * 2
    assert compute_backoff(3) == INITIAL_BACKOFF * 4
    # high attempts cap at MAX_BACKOFF
    assert compute_backoff(20) == MAX_BACKOFF


# ---- dispatch_event ---------------------------------------------------------


class _FakeDB:
    def __init__(self, subscriptions):
        self.subscriptions = subscriptions
        self.added = []
        self.flushed = False

    def add(self, item):
        self.added.append(item)

    async def flush(self):
        self.flushed = True
        for d in self.added:
            if getattr(d, "id", None) is None:
                d.id = uuid4()

    async def execute(self, _stmt):
        # The dispatch_event WHERE filters by is_active and events; here we just
        # return the pre-filtered list the test supplies.
        rows = self.subscriptions

        class _R:
            def scalars(self_inner):
                class _S:
                    def all(self_innermost):
                        return rows

                return _S()

        return _R()


@pytest.mark.asyncio
async def test_dispatch_event_creates_one_delivery_per_active_matching_sub() -> None:
    s1 = WebhookSubscription(
        url="https://a", events=["application.assigned"], secret="x", is_active=True
    )
    s1.id = uuid4()
    s2 = WebhookSubscription(
        url="https://b", events=["*"], secret="y", is_active=True
    )
    s2.id = uuid4()
    db = _FakeDB([s1, s2])

    deliveries = await dispatch_event(
        db,
        event="application.assigned",
        data={"application_id": "abc"},
    )
    assert len(deliveries) == 2
    assert all(d.status == "pending" for d in deliveries)
    assert {d.subscription_id for d in deliveries} == {s1.id, s2.id}
    assert db.flushed


@pytest.mark.asyncio
async def test_dispatch_event_no_subscriptions_skips_flush() -> None:
    db = _FakeDB([])
    deliveries = await dispatch_event(db, event="nothing", data={})
    assert deliveries == []
    assert not db.flushed


# ---- deliver_pending: HTTP + retry --------------------------------------------


class _FakeClient:
    """In-memory httpx client double; records requests and returns scripted responses."""

    def __init__(self, responses: list):
        self._responses = list(responses)
        self.requests = []

    async def post(self, url, content, headers):
        self.requests.append({"url": url, "content": content, "headers": dict(headers)})
        resp = self._responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        status_code, body = resp
        return httpx.Response(status_code, content=body)

    async def aclose(self):
        return None


def _make_subscription(*, url="https://example.com/hook", events=None) -> WebhookSubscription:
    s = WebhookSubscription(
        url=url,
        events=events or ["*"],
        secret="shh",
        is_active=True,
    )
    s.id = uuid4()
    return s


def _make_delivery(subscription_id, *, attempts=0, scheduled=None) -> WebhookDelivery:
    n = _now()
    d = WebhookDelivery(
        subscription_id=subscription_id,
        event="application.assigned",
        payload={"hello": "world"},
        status="pending",
        attempts=attempts,
        scheduled_for=scheduled or n,
        created_at=n,
    )
    d.id = uuid4()
    return d


class _DeliveryDB:
    """Fake DB that supports _claim_pending + commits."""

    def __init__(self, pairs: list):
        self._pairs = pairs  # list of (delivery, subscription)
        self.committed = False
        self._call = 0

    async def execute(self, stmt):
        self._call += 1
        text = str(stmt).lower()
        # 1st: select id list of pending — return all that are pending + due
        if self._call == 1:
            now = _now()
            ids = [
                d.id for d, _ in self._pairs
                if d.status == "pending" and d.scheduled_for <= now
            ]

            class _R:
                def scalars(self_inner):
                    class _S:
                        def all(self_innermost):
                            return ids

                    return _S()

            return _R()
        # 2nd: UPDATE ... RETURNING id — flip them to in_progress
        if "update " in text and "returning" in text:
            now = _now()
            updated = []
            for d, _ in self._pairs:
                if d.status == "pending" and d.scheduled_for <= now:
                    d.status = "in_progress"
                    updated.append(SimpleNamespace(id=d.id))

            class _R:
                def all(self_inner):
                    return updated

            return _R()
        # 3rd: SELECT delivery + sub for claimed ids
        rows = [(d, s) for d, s in self._pairs if d.status == "in_progress"]

        class _R:
            def all(self_inner):
                return rows

        return _R()

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_deliver_pending_success_marks_sent_and_signs_payload() -> None:
    sub = _make_subscription()
    delivery = _make_delivery(sub.id)
    db = _DeliveryDB([(delivery, sub)])
    client = _FakeClient(responses=[(204, b"")])

    results = await deliver_pending(db, limit=10, client=client)

    assert len(results) == 1
    assert results[0].succeeded
    assert delivery.status == "sent"
    assert delivery.delivered_at is not None
    assert delivery.attempts == 1
    # signature is sha256= prefix on hmac of body
    sig_header = client.requests[0]["headers"][SIGNATURE_HEADER]
    assert sig_header.startswith("sha256=")
    body = client.requests[0]["content"]
    assert verify_signature("shh", body, sig_header)
    # Payload envelope structure
    payload = json.loads(body)
    assert payload["event"] == "application.assigned"
    assert payload["data"] == {"hello": "world"}
    # Delivery id header set
    assert client.requests[0]["headers"][DELIVERY_ID_HEADER] == str(delivery.id)
    assert db.committed


@pytest.mark.asyncio
async def test_deliver_pending_failure_schedules_retry() -> None:
    sub = _make_subscription()
    delivery = _make_delivery(sub.id, attempts=0)
    db = _DeliveryDB([(delivery, sub)])
    client = _FakeClient(responses=[(500, b"boom")])

    before = _now()
    results = await deliver_pending(db, limit=10, client=client)

    assert not results[0].succeeded
    assert delivery.status == "pending"  # back to retry queue
    assert delivery.attempts == 1
    assert delivery.last_status_code == 500
    assert delivery.scheduled_for >= before + INITIAL_BACKOFF - timedelta(seconds=2)


@pytest.mark.asyncio
async def test_deliver_pending_marks_dead_after_max_attempts() -> None:
    sub = _make_subscription()
    delivery = _make_delivery(sub.id, attempts=MAX_ATTEMPTS - 1)
    db = _DeliveryDB([(delivery, sub)])
    client = _FakeClient(responses=[(500, b"boom")])

    await deliver_pending(db, limit=10, client=client)

    assert delivery.status == "dead"
    assert delivery.attempts == MAX_ATTEMPTS


@pytest.mark.asyncio
async def test_deliver_pending_handles_network_exception() -> None:
    sub = _make_subscription()
    delivery = _make_delivery(sub.id)
    db = _DeliveryDB([(delivery, sub)])
    client = _FakeClient(responses=[httpx.ConnectError("dns blew up")])

    results = await deliver_pending(db, limit=10, client=client)

    assert not results[0].succeeded
    assert results[0].status_code is None
    assert "dns blew up" in (delivery.last_error or "")
    assert delivery.status == "pending"
