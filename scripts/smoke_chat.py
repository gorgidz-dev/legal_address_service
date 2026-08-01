"""Боевой прогон общей переписки — от создания ветки до скачивания вложения.

Запускается ТОЛЬКО против отдельной пустой базы (DATABASE_URL=...chat_smoke),
и первым делом в этом убеждается: скрипт пишет данные и рассчитывает на то,
что кроме него в базе никого нет.

Что проверяется помимо «не падает»: подпись автора глазами разных читателей,
изоляция вложений между ветками, счётчик непрочитанного и отказ на файле,
который браузер мог бы отрисовать как страницу.
"""
from __future__ import annotations

import asyncio
import secrets
import sys
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from httpx import ASGITransport, AsyncClient

from app.auth import utcnow
from app.config import settings
from app.database import AsyncSessionLocal
from app.enums import AddressPublicationStatus, UserRole
from app.main import app
from app.models.address import Address
from app.models.provider import Provider
from app.models.user import User
from app.models.user_session import UserSession
from app.services.auth_security import hash_token
from app.services.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME

FAILURES: list[str] = []


def check(condition: bool, label: str) -> None:
    print(f"  {'OK  ' if condition else 'FAIL'} {label}")
    if not condition:
        FAILURES.append(label)


async def seed() -> dict:
    async with AsyncSessionLocal() as db:
        provider = Provider(
            code=f"smoke-{uuid4().hex[:8]}",
            full_name='ООО "Смоук"',
            short_name="ООО Смоук",
        )
        db.add(provider)
        await db.flush()

        address = Address(
            provider_id=provider.id,
            full_address="г. Москва, ул. Смоуковая, д. 1",
            cadastral_number="77:01:0001001:1",
            ownership_doc="Свидетельство",
            ownership_doc_short="Св-во",
            ownership_doc_pages=1,
            price_6m=Decimal("30000"),
            price_11m=Decimal("45000"),
            publication_status=AddressPublicationStatus.PUBLISHED.value,
            is_available=True,
        )
        db.add(address)

        client = User(
            email="smoke-client@example.com",
            full_name="Клиент Смоукин",
            role=UserRole.CLIENT.value,
        )
        stranger = User(
            email="smoke-stranger@example.com",
            full_name="Чужой Клиент",
            role=UserRole.CLIENT.value,
        )
        owner = User(
            email="smoke-owner@example.com",
            full_name="Собственник Иванов",
            role=UserRole.OWNER.value,
            provider_id=provider.id,
        )
        lawyer = User(
            email="smoke-lawyer@example.com",
            full_name="Юрист Петрова",
            role=UserRole.LAWYER.value,
        )
        db.add_all([client, stranger, owner, lawyer])
        await db.flush()

        # Настоящие сессии, а не подмена зависимости: вход проверяет middleware
        # до роутера, и обойти её значило бы протестировать не тот путь.
        tokens = {}
        now = utcnow()
        for key, user in (
            ("client", client),
            ("stranger", stranger),
            ("owner", owner),
            ("lawyer", lawyer),
        ):
            raw = secrets.token_urlsafe(32)
            db.add(
                UserSession(
                    user_id=user.id,
                    token_hash=hash_token(raw),
                    expires_at=now + timedelta(hours=12),
                    created_at=now,
                    session_type="web",
                )
            )
            tokens[key] = raw

        await db.commit()
        return {"address_id": address.id, "tokens": tokens}


async def main() -> int:
    if "chat_smoke" not in settings.database_url:
        print("Отказ: скрипт пишет данные и запускается только на базе chat_smoke.")
        return 2

    ids = await seed()
    tokens = ids["tokens"]
    csrf = secrets.token_urlsafe(16)

    def login_as(who: str) -> None:
        http.cookies.clear()
        http.cookies.set(settings.session_cookie_name, tokens[who])
        http.cookies.set(CSRF_COOKIE_NAME, csrf)

    transport = ASGITransport(app=app)

    async with AsyncClient(
        transport=transport, base_url="http://smoke", headers={CSRF_HEADER_NAME: csrf}
    ) as http:
        login_as("client")
        print("\n== ветка ==")
        r = await http.post(f"/api/v1/chats/addresses/{ids['address_id']}")
        check(r.status_code == 200, f"клиент открыл ветку ({r.status_code})")
        chat = r.json()
        chat_id = chat["id"]
        check(chat["provider_name"] == "ООО Смоук", "в ветке видна организация")

        print("\n== текстовое сообщение ==")
        r = await http.post(
            f"/api/v1/chats/{chat_id}/messages", json={"body": "Здравствуйте, адрес свободен?"}
        )
        check(r.status_code == 200, f"клиент написал ({r.status_code})")

        print("\n== вложение от собственника ==")
        login_as("owner")
        pdf = b"%PDF-1.4 smoke test payload"
        r = await http.post(
            f"/api/v1/chats/{chat_id}/messages/upload",
            data={"body": "Договор во вложении"},
            files={"files": ("Договор.pdf", pdf, "application/pdf")},
        )
        check(r.status_code == 200, f"собственник приложил файл ({r.status_code})")
        message = r.json()
        check(len(message.get("attachments", [])) == 1, "вложение вернулось в ответе")
        attachment = message["attachments"][0]
        check(attachment["original_filename"] == "Договор.pdf", "имя файла сохранено")
        check(attachment["size_bytes"] == len(pdf), "размер совпал")

        print("\n== файл без текста ==")
        r = await http.post(
            f"/api/v1/chats/{chat_id}/messages/upload",
            data={"body": ""},
            files={"files": ("Акт.pdf", b"%PDF-1.4 act", "application/pdf")},
        )
        check(r.status_code == 200, f"сообщение из одного файла принято ({r.status_code})")

        print("\n== опасный файл ==")
        r = await http.post(
            f"/api/v1/chats/{chat_id}/messages/upload",
            data={"body": "вот"},
            files={"files": ("письмо.html", b"<script>alert(1)</script>", "image/png")},
        )
        check(r.status_code == 422, f"html отклонён, несмотря на content-type картинки ({r.status_code})")

        print("\n== пустое сообщение ==")
        r = await http.post(f"/api/v1/chats/{chat_id}/messages", json={"body": "   "})
        check(r.status_code == 422, f"пустое сообщение отклонено ({r.status_code})")

        print("\n== подпись автора ==")
        login_as("lawyer")
        r = await http.post(
            f"/api/v1/chats/{chat_id}/messages", json={"body": "Площадка проверит комплект."}
        )
        check(r.status_code == 200, f"юрист участвует в переписке ({r.status_code})")

        r = await http.get(f"/api/v1/chats/{chat_id}/messages")
        check(r.status_code == 200, f"юрист читает историю ({r.status_code})")
        staff_view = r.json()
        sides = [m["author_side"] for m in staff_view]
        check(sides == ["client", "owner", "owner", "staff"], f"стороны определены: {sides}")
        check(
            staff_view[3]["author_name"] == "Юрист Петрова",
            "коллеге видно, кто из площадки ответил",
        )
        check(staff_view[1]["author_name"] == "ООО Смоук", "собственник подписан организацией")

        login_as("client")
        r = await http.get(f"/api/v1/chats/{chat_id}/messages")
        client_view = r.json()
        check(
            client_view[3]["author_name"] == "Площадка",
            "клиенту имя оператора не показано",
        )
        check(len(client_view[1]["attachments"]) == 1, "клиент видит вложение собственника")

        print("\n== скачивание ==")
        url = client_view[1]["attachments"][0]["download_url"]
        r = await http.get(f"/api/v1{url}")
        check(r.status_code == 200, f"клиент скачал вложение ({r.status_code})")
        check(r.content == pdf, "содержимое файла совпало")
        check(
            r.headers.get("x-content-type-options") == "nosniff",
            "заголовок nosniff на месте",
        )
        check(
            "attachment" in (r.headers.get("content-disposition") or ""),
            "файл отдаётся вложением, а не страницей",
        )

        print("\n== чужой ==")
        login_as("stranger")
        r = await http.get(f"/api/v1/chats/{chat_id}/messages")
        check(r.status_code == 403, f"посторонний клиент не читает чужую ветку ({r.status_code})")
        r = await http.get(f"/api/v1{url}")
        check(r.status_code == 403, f"посторонний не скачивает вложение ({r.status_code})")

        print("\n== непрочитанное ==")
        login_as("client")
        r = await http.get("/api/v1/chats")
        rows = r.json()
        check(len(rows) == 1, "клиент видит только свою ветку")
        # Своё сообщение не считается; после него написали собственник (2) и юрист (1).
        check(rows[0]["unread_count"] == 3, f"счётчик непрочитанного = {rows[0]['unread_count']}")

        r = await http.post(f"/api/v1/chats/{chat_id}/read")
        check(r.status_code == 204, f"отметка о прочтении ({r.status_code})")
        rows = (await http.get("/api/v1/chats")).json()
        check(rows[0]["unread_count"] == 0, "после прочтения счётчик обнулился")

        login_as("owner")
        rows = (await http.get("/api/v1/chats")).json()
        # Отправка помечает ветку прочитанной, поэтому вопрос клиента для
        # собственника уже не новый — новым осталось только сообщение юриста,
        # пришедшее позже. Счётчик у каждого свой, и это ровно то поведение,
        # которого ждёшь от переписки на троих.
        check(
            rows[0]["unread_count"] == 1,
            f"у собственника непрочитано только сообщение юриста: {rows[0]['unread_count']}",
        )

    print("\n" + ("ВСЁ ЗЕЛЁНОЕ" if not FAILURES else f"ПРОВАЛЫ: {FAILURES}"))
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
