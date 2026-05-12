from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.incoming_webhook import IncomingWebhook
from app.routers.webhooks import inbound_payment_webhook
from app.services.webhooks import SIGNATURE_HEADER, sign_payload


class _FakeRequest:
    def __init__(self, body: bytes, sig: str | None):
        self._body = body
        self.headers = {SIGNATURE_HEADER: sig} if sig else {}

    async def body(self) -> bytes:
        return self._body


class _FakeDB:
    def __init__(self, *, raise_integrity_on_commit: bool = False):
        self.added: list[IncomingWebhook] = []
        self.committed = False
        self.rolled_back = False
        self._raise = raise_integrity_on_commit

    def add(self, item):
        self.added.append(item)

    async def commit(self):
        if self._raise:
            raise IntegrityError("dup key", params=None, orig=Exception("uniq"))
        self.committed = True

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_inbound_payment_webhook_returns_503_when_secret_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_webhook_secret", "")
    req = _FakeRequest(b"{}", None)
    db = _FakeDB()
    with pytest.raises(HTTPException) as info:
        await inbound_payment_webhook("yookassa", req, db)
    assert info.value.status_code == 503


@pytest.mark.asyncio
async def test_inbound_payment_webhook_rejects_bad_signature(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_webhook_secret", "topsecret")
    body = json.dumps({"id": "evt_1"}).encode()
    req = _FakeRequest(body, "sha256=deadbeef")
    db = _FakeDB()
    with pytest.raises(HTTPException) as info:
        await inbound_payment_webhook("yookassa", req, db)
    assert info.value.status_code == 401
    assert info.value.detail["code"] == "bad_signature"


@pytest.mark.asyncio
async def test_inbound_payment_webhook_stores_event_on_valid_signature(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_webhook_secret", "topsecret")
    body = json.dumps({"id": "evt_42", "event": "payment.succeeded", "amount": 1500}).encode()
    sig = sign_payload("topsecret", body)
    req = _FakeRequest(body, sig)
    db = _FakeDB()

    result = await inbound_payment_webhook("yookassa", req, db)

    assert result == {"received": True, "replayed": False}
    assert db.committed
    assert len(db.added) == 1
    saved = db.added[0]
    assert saved.provider == "yookassa"
    assert saved.external_id == "evt_42"
    assert saved.event_type == "payment.succeeded"
    assert saved.raw_body["amount"] == 1500


@pytest.mark.asyncio
async def test_inbound_payment_webhook_idempotent_on_replay(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_webhook_secret", "topsecret")
    body = json.dumps({"id": "evt_42"}).encode()
    sig = sign_payload("topsecret", body)
    req = _FakeRequest(body, sig)
    db = _FakeDB(raise_integrity_on_commit=True)

    result = await inbound_payment_webhook("yookassa", req, db)

    assert result == {"received": True, "replayed": True}
    assert db.rolled_back


@pytest.mark.asyncio
async def test_inbound_payment_webhook_requires_event_id(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_webhook_secret", "topsecret")
    body = json.dumps({"event": "no_id_field"}).encode()
    sig = sign_payload("topsecret", body)
    req = _FakeRequest(body, sig)
    db = _FakeDB()
    with pytest.raises(HTTPException) as info:
        await inbound_payment_webhook("yookassa", req, db)
    assert info.value.status_code == 422
    assert info.value.detail["code"] == "missing_event_id"


@pytest.mark.asyncio
async def test_inbound_payment_webhook_rejects_invalid_json(monkeypatch) -> None:
    monkeypatch.setattr(settings, "payment_webhook_secret", "topsecret")
    body = b"not json at all"
    sig = sign_payload("topsecret", body)
    req = _FakeRequest(body, sig)
    db = _FakeDB()
    with pytest.raises(HTTPException) as info:
        await inbound_payment_webhook("yookassa", req, db)
    assert info.value.status_code == 422
    assert info.value.detail["code"] == "bad_json"
