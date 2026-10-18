# uradres.net — контекст для Claude Code

Маркетплейс юридических адресов (РФ): собственники публикуют помещения, клиенты
покупают право использовать адрес для регистрации юрлица или смены адреса в ЕГРЮЛ;
площадка готовит договоры и гарантийные письма. Юрлицо — ООО «Юрадрес.Нет», **ОСН**.

Этот файл — главная точка входа. Прочитай его целиком, а по оплате — ещё
`docs/tbank-acquiring.md`: там все факты по Т-Банку, перепроверенные по первоисточнику
(не гуглить заново).

## Как устроены деньги (модель площадки, со слов владельца 12.10.2026)

Цену адреса (за 6 или 11 месяцев) задаёт собственник; **комиссия площадки уже внутри
этой цены** (по умолчанию **19%**, у собственника может быть свой процент), клиенту
сверху ничего не добавляется. Возврат клиенту после оказания услуги — **индивидуально**,
решает админ (система его не блокирует). Кто кому платит — по типу заявки:

- **Первичная регистрация** (`initial_registration`): клиент платит **всю сумму
  площадке** (СБП → Т-Банк). Площадка перечисляет собственнику цену **за вычетом
  своей комиссии** — и **только после успешной регистрации** компании клиента по
  адресу (решение владельца 12.10.2026). Механизм — ветка `feat/owner-payouts`
  (`app/services/owner_payouts.py`, `docs/owner-payouts.md`).
- **Смена адреса** (`address_change`): **счёт клиенту выставляет собственник**
  (`manual_invoice`: собственник загружает счёт, клиент — платёжку, собственник
  подтверждает получение). Потом **собственник сам платит площадке комиссию**.
  Расхождение с кодом: `manual_invoice` заводится только при `payer_type=juridical`;
  смена адреса с плательщиком-физлицом сейчас идёт через СБП площадке.

**Регистрация компании** (статус-трекер, этап 6): клиент загружает PDF расписки ИФНС
из письма (только его, без сканов), собственник видит расписку, админ подтверждает
регистрацию по ЕГРЮЛ — первичная по **названию + адресу**, смена адреса по **ИНН +
адресу** (решения владельца 13.10.2026). Образец бланка — обезличенно в
`tests/test_ifns_receipt.py` (настоящий файл с персональными данными в репозиторий не класть).

Тексты сайта и расчёты держать в рамках этой модели: «аренду» площадка не продаёт и
договор аренды не заключает (он между клиентом и собственником, оферта п. 2).
**Открытый вопрос к бухгалтеру** — чеки при первичной регистрации, см.
`docs/tbank-acquiring.md` §10, вопрос 6.

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
- Ветка **`feat/tbank-acquiring`** (в GitHub с 2026-09-21) — интернет-эквайринг Т-Банка,
  в `main` не слита и в прод не выкатывалась:
  - `f9df82e` бэкенд (Init/GetState/Cancel, уведомления, сверка, возвраты);
  - `6ee2d13` веб-кнопка «Оплатить» по руководству НСПК + страница возврата из банка;
  - `722efe8` мобайл: оплата во встроенной вкладке (url_launcher);
  - `dd0d769` решения владельца: своя касса, ОСН, НДС 22%, ФН-36;
  - `56123f3` чеки 54-ФЗ: предоплата в Init, закрывающий при выдаче документов.
- **Что осталось по оплате:**
  1. `Init` с `Receipt` DEMO-терминал принял (12.10.2026, `smoke_tbank.py` с
     `TBANK_RECEIPTS_ENABLED=true` — всё зелёное). Осталось: закрывающий чек
     (`SendClosingReceipt`, формат `Payments`) — нужен DEMO-платёж, оплаченный руками
     тестовой картой. С Mac банк доступен только через туннель на прод
     (`ssh -N -D 1080 uradres-prod`, запускает владелец) + `HTTPS_PROXY=socks5://127.0.0.1:1080`.
  2. **18.10.2026 владелец сообщил: эквайринг и касса подключены** (боевой терминал и
     облачная касса в ЛК эквайринга). При подключённой кассе банк требует чек в каждом
     `Init` — значит, `PAYMENT_PROVIDER=tbank` на проде только вместе с
     `TBANK_RECEIPTS_ENABLED=true`.
  3. Запуск: слить ветки в `main` и задеплоить (оплата при этом не меняется), владелец
     вписывает боевые ключи в `.env.production`, включаем `tbank` + чеки, первая боевая
     оплата на малую сумму: чек предоплаты → выдача документов → закрывающий чек
     (формат `Payments` живьём ещё не проверен) → возврат. Каждый шаг — по просьбе владельца.
  4. Вопросы бухгалтеру: **агент или собственная услуга** при первичной регистрации
     (от ответа зависят чек и НДС — `docs/tbank-acquiring.md` §10, вопрос 6) и единица
     измерения в чеке — «шт» или «иная».
  5. Кнопки админа для закрывающего чека — сделаны (12.10.2026): «Заявки» → «Чек» у заявок
     с выданными документами (`ClosingReceiptPanel` в `App.tsx`).
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
- `owner-payouts.md` — выплаты собственникам: как устроены, роли, проверки.
- `accountant-question-settlements.md` — вопрос бухгалтеру: агент или своя услуга, чеки,
  НДС, документы на выплаты собственникам (ответа пока нет).
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

## Локальная разработка (macOS)

- С 2026-09-21 работа идёт на MacBook. **Homebrew и прав администратора нет** — всё в
  пользовательском пространстве: `uv` в `~/.local/bin` (`export PATH="$HOME/.local/bin:$PATH"`),
  Node 22 в `~/development/node22/bin`, Docker = Colima (`colima start --vm-type vz`).
- Системный `git`/`python3` (шимы xcrun) падают на «not agreed to the Xcode license» —
  использовать `/Applications/Xcode.app/Contents/Developer/usr/bin/git` либо один раз
  выполнить в Терминале `sudo xcodebuild -license accept`.
- Python: `uv venv --python 3.12 .venv && uv pip install --python .venv/bin/python -r requirements.txt`.
- Postgres — контейнер `uradres-pg` (образ `postgres:16`, порт **5433**, чтобы не мешать
  `nearby-db` на 5432): `docker run -d --name uradres-pg -e POSTGRES_PASSWORD=postgres
  -e POSTGRES_DB=legal_address -p 5433:5432 postgres:16`; повторно — `docker start uradres-pg`.
  В `.env` прописан `DATABASE_URL=...@localhost:5433/legal_address`. Смоук-базы:
  `docker exec uradres-pg createdb -U postgres tbank_smoke` (в `DATABASE_URL` менять имя базы).
- Миграции `.venv/bin/alembic upgrade head`. Тесты — **только** `.venv/bin/python -m pytest -q`
  (голый `pytest` не видит пакет `app`).
- **Т-Банк с этого Mac недоступен**: выход в интернет через Германию (VPN), банк режет
  не-российские IP (таймаут даже на `www.tbank.ru`). Для живых смоуков — либо выключить VPN,
  либо SOCKS через прод: `ssh -N -D 1080 uradres-prod` и `HTTPS_PROXY=socks5://127.0.0.1:1080`
  (нужен пакет `socksio`; трогает только сеть сервера).
- GitHub: пуш по SSH-алиасу `github-uradres` (ключ `~/.ssh/uradres-github`), если его
  публичная часть добавлена в GitHub; иначе — HTTPS со входом в GitHub.

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
  - `scripts/smoke_owner_payouts.py` — выплаты собственникам (база `payouts_smoke`,
    DaData подменена; инструкция в шапке);
  - `scripts/smoke_registration_tracker.py` — статус-трекер: расписка ИФНС, сверка
    регистрации, напоминания (база `tracker_smoke`; DaData и чтение PDF подменены);
  - `scripts/smoke_chat.py` — чат и вложения; на проде гонять в режиме S3 (без
    переопределения `APP_ENV`/`STORAGE_BACKEND`) на отдельной базе.
- Интерфейс на проде без пароля: в контейнере backend заводится временная
  `UserSession` (`device_name="ui-check-temp"`), токен кладётся в куку
  `legal_address_session` через `document.cookie`; после проверки сессии отозвать,
  созданные данные удалить.
- Браузерная панель: скриншоты часто не работают — проверять через `read_page` и
  `javascript_tool`, предварительно задав `resize_window` с явными размерами.
