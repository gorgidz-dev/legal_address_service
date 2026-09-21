# uradres.net — контекст для Claude Code

Маркетплейс юридических адресов (РФ): собственники публикуют помещения, клиенты
покупают право использовать адрес для регистрации юрлица или смены адреса в ЕГРЮЛ;
площадка готовит договоры и гарантийные письма. Юрлицо — ООО «Юрадрес.Нет», **ОСН**.

Этот файл — главная точка входа. Прочитай его целиком, а по оплате — ещё
`docs/tbank-acquiring.md`: там все факты по Т-Банку, перепроверенные по первоисточнику
(не гуглить заново).

## Правила владельца (действуют всегда)

- **Не пушить, не деплоить и не включать `PAYMENT_PROVIDER=tbank` на проде** без явной
  просьбы. Каждый пуш и деплой — отдельное разрешение.
- **Боевые пароли и ключи в чат не брать.** Владелец сам вписывает их в
  `.env.production` на сервере. DEMO-ключи Т-Банка — только в локальном `.env`
  (он в `.gitignore`).
- **Пароли в веб-формы не вводить.** Для проверки интерфейса на проде — временная
  сессия (рецепт ниже).
- Секреты не коммитить. Репозиторий **публичный**.
- Скачивать файлы — только с явного разрешения.
- Отвечать и пояснять по-русски, простыми словами. Мелкие правки делать самому, без
  субагентов: владелец следит за расходом токенов.
- Каждый осмысленный этап — отдельный коммит. Поведение не менять без задачи.

## Где мы сейчас (2026-09-21)

- `main` = прод. Оплата на проде — по-прежнему `cdek_pay` (фактически выключена:
  ключей нет, initiate → 503).
- Ветка **`feat/tbank-acquiring`** — интернет-эквайринг Т-Банка, в прод не выкатывалась:
  - `f9df82e` бэкенд (Init/GetState/Cancel, уведомления, сверка, возвраты);
  - `6ee2d13` веб-кнопка «Оплатить» по руководству НСПК + страница возврата из банка;
  - `722efe8` мобайл: оплата во встроенной вкладке (url_launcher);
  - `dd0d769` решения владельца: своя касса, ОСН, НДС 22%, ФН-36;
  - `56123f3` чеки 54-ФЗ: предоплата в Init, закрывающий при выдаче документов.
- **Что осталось по оплате:**
  1. Проверить живьём на DEMO-терминале, что банк принимает наш `Receipt`
     (`scripts/smoke_tbank.py` с `TBANK_RECEIPTS_ENABLED=true`). С IP песочницы
     Т-Банк бывает недоступен целиком — тогда ждать.
  2. Владелец подключает кассу OFD Ferma (почековый тариф + ФН-36) и привязывает её к
     терминалу в ЛК эквайринга (ФФД 1.2, СНО ОСН, сайт uradres.net).
  3. Только после этого — `TBANK_RECEIPTS_ENABLED=true` и боевой терминал на проде.
  4. Вопрос бухгалтеру: единица измерения в чеке — «шт» или «иная».
  5. Кнопок админа для закрывающего чека в интерфейсе нет (только API
     `POST /payments/{id}/closing-receipt` и алерты) — делать, если попросят.
- Отложено владельцем: сделать репозиторий приватным.

## Стек и ключевые файлы

- Бэкенд: FastAPI + SQLAlchemy async + asyncpg + Alembic + Pydantic v2 (`app/`).
  Точка входа `app/main.py`, настройки `app/config.py`, статусы `app/enums.py`.
- Фронтенд: React 19 + Vite + TS (`frontend/`). Роутера нет — экраны переключаются
  через state; публичная часть `publicCatalog.tsx` + `sections/`, кабинеты — `App.tsx`.
  Токены дизайн-системы: `--ds-*` (публичная), `--lg-*` (кабинеты).
- Мобайл: Flutter (`mobile/`), клиентское приложение.
- Оплата: `app/services/tbank_acquiring.py` (клиент банка), `tbank_payments.py`
  (состояния платежа), `tbank_receipts.py` (чеки), `app/routers/payments.py`,
  `app/routers/webhooks.py`, крон `scripts/reconcile_tbank_payments.py`.
- Заявки: `app/routers/workflow.py`, `app/services/application_workflow.py`.
- Чат: `app/services/chat_threads.py`, `chat_attachments.py`.

Статусы заявки: `draft` → `awaiting_payment` → `paid` → `admin_review` →
`assigned_to_owner` → `accepted_by_owner` → `documents_preparing` →
`documents_uploaded` → `documents_review` → `ready_for_client` → `completed`.
Боковые: `needs_client_fix`, `documents_revision`, `rejected_by_owner`, `cancelled`,
`dispute`, `refund_pending`, `refunded`. Значения enum не менять — от них зависит мобайл.

## Документы в `docs/`

- `tbank-acquiring.md` — эквайринг, чеки, решения владельца (§9–§10).
- `roadmap-2026-07-feedback.md` — 18 правок заказчика и этапы.
- `runbook.md`, `deploy-selectel.md`, `security-checklist.md`, `mobile-api.md`, `design.md`.

## Прод

- Сервер **139.100.237.19** (Selectel), вход: `ssh uradres-prod` (алиас в
  `~/.ssh/config`, ключ `~/.ssh/uradres-deploy`, пользователь root). Репо на сервере —
  `/root/legal_address_service`, ветка `main`; `.env.production` лежит рядом, в git нет.
- SSH иногда рвётся на «banner exchange» — повторять, ставить
  `-o ConnectionAttempts=6 -o ConnectTimeout=45`.
- Деплой (только по просьбе):
  `ssh uradres-prod 'cd /root/legal_address_service && git pull --ff-only origin main && bash scripts/deploy.sh'`.
  В образ код попадает только через `deploy.sh` (пересборка); одного `git pull` мало.
  Миграции выполняются до переключения контейнеров — поэтому только аддитивные.
- Контейнеры: caddy (TLS) + frontend (nginx) + backend + db (postgres:16).
- Скрипт на проде: `docker compose --env-file .env.production run --rm backend python -m scripts.<name>`.
  Перед изменением данных — бэкап `bash deploy/backup-db.sh` → `/root/backups/`.
  Сервер живёт по UTC.
- Cron: бэкап 04:15, healthcheck каждые 5 минут, напоминания 06:10 и 06:20 UTC. Задания
  описаны в `deploy/setup-ops.sh` — при добавлении нового дополнять и фильтр пересборки
  crontab там же, иначе повторный прогон плодит дубли.
- Проверка после деплоя: локальный `curl` к https://uradres.net на Windows падает на
  schannel — проверять с самого сервера или через браузерную панель.
- Данные прода демонстрационные (28 адресов, 10 городов, все из seed-скриптов).

## Локальная разработка (Windows)

- Python: через PyManager (`py install 3.12`), затем `py -3.12 -m venv .venv` и
  `.venv\Scripts\pip install -r requirements.txt`. Тесты: `.venv\Scripts\python -m pytest -q`.
- Postgres: системного нет. Рецепт: официальные бинарники EnterpriseDB
  (`postgresql-16.x-windows-x64-binaries.zip`), распаковать **системным**
  `C:\Windows\System32\tar.exe -xf` (tar из Git Bash zip не берёт) в постоянный путь
  (было `C:\src\pgsql`, данные `C:\src\pgsql-data`, порт **5433**):
  `initdb -D <data> -U postgres --auth=trust -E UTF8 --locale=C`,
  `pg_ctl -D <data> -o "-p 5433" -l pg.log start`.
- Бэкенд с фронтом на одном origin: собрать `frontend` (`npm ci && npm run build`), потом
  `APP_ENV=development python -m uvicorn app.main:app --port 8010`. Демо-данные:
  POST `/api/v1/auth/bootstrap-admin`, затем POST `/api/v1/demo/seed` `{"password":"demo12345"}`.
- Локальный бэкенд отдаёт только `/` и `/invite`; глубокие пути на проде обслуживает
  nginx `try_files`.

## Как проверять

- **Юнит-тесты работают на подставных сессиях и не видят SQL.** Всё, что пишет в базу,
  проверять ещё и смоуком на настоящем Postgres. Реальные баги, дошедшие до прода мимо
  pytest: миграция без `server_default` у `id`, невалидный `desc(col.nullslast())`,
  чтение ORM-объектов после rollback (MissingGreenlet), JSONB без `none_as_null=True`
  (Python `None` пишется как JSON `null`, и `IS NOT NULL` его находит).
- Смоуки — только на отдельной базе, которую потом удалить:
  - `scripts/smoke_tbank.py` — живой DEMO-терминал; база `tbank_smoke`, env
    `PAYMENT_PROVIDER=tbank`, DEMO-ключи из `.env`,
    `TBANK_TEST_PAYER_EMAILS=smoke-tbank-client@example.com`,
    `TBANK_NOTIFICATION_URL=https://example.com/uradres-smoke-noop`; перед запуском
    `dropdb/createdb` и `alembic upgrade head`, запуск `python -X utf8 -m scripts.smoke_tbank`;
  - `scripts/smoke_tbank_receipts.py` — чеки с подменённым банком (инструкция в шапке);
  - `scripts/smoke_chat.py` — чат и вложения; на проде гонять в режиме S3 (без
    переопределения `APP_ENV`/`STORAGE_BACKEND`) на отдельной базе.
- Интерфейс на проде без пароля: в контейнере backend заводится временная
  `UserSession` (`device_name="ui-check-temp"`), токен кладётся в куку
  `legal_address_session` через `document.cookie`; после проверки сессии отозвать,
  созданные данные удалить.
- Браузерная панель: скриншоты часто не работают — проверять через `read_page` и
  `javascript_tool`, предварительно задав `resize_window` с явными размерами.
