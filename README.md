# Сервис юридических адресов

Маркетплейс юридических адресов (РФ): собственники публикуют помещения, клиенты
покупают право использовать адрес для регистрации ЮЛ или смены адреса в ЕГРЮЛ.
Сервис автоматизирует заявки, оплату, генерацию договоров и гарантийных писем.

Роли: `client` (клиент), `owner` (собственник помещения), `admin` (оператор
площадки); legacy-роли `manager` / `lawyer` для внутренних операций.

## Стек

**Бэкенд** — FastAPI, SQLAlchemy (async) + asyncpg, PostgreSQL, Alembic,
Pydantic v2, `docxtpl` для генерации DOCX, локальное или S3-совместимое
хранилище. **Фронтенд** — React + Vite + TypeScript.
**Деплой** — Docker Compose (postgres + backend + nginx-фронт) за Caddy (TLS).

## Структура

```
legal_address_service/
├── app/                     ← бэкенд FastAPI
│   ├── main.py              ← точка входа, auth-middleware, роутинг
│   ├── config.py            ← настройки (pydantic-settings) + prod-hardening
│   ├── models/              ← SQLAlchemy-модели
│   ├── schemas/             ← Pydantic-схемы запросов/ответов
│   ├── routers/             ← HTTP/WS-эндпоинты
│   └── services/            ← бизнес-логика (auth, платежи, документы, DaData…)
├── alembic/versions/        ← миграции БД (0001…0025, линейная цепочка)
├── frontend/                ← SPA (React + Vite)
├── tests/                   ← pytest (300+ тестов)
├── scripts/                 ← вспомогательные скрипты (генерация шаблонов/ключей)
├── templates/               ← .docx-шаблоны договоров и гарантийных писем
├── docs/                    ← runbook, security-checklist, deploy-заметки
├── Dockerfile, docker-compose.yml, Caddyfile, frontend/nginx.conf
└── .env.example, .env.production.example
```

## Локальный запуск

```bash
# 1. Виртуальное окружение + зависимости
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Конфиг: скопировать пример и заполнить (как минимум DATABASE_URL)
cp .env.example .env

# 3. Применить миграции к PostgreSQL
alembic upgrade head

# 4. Запустить API (http://127.0.0.1:8000, Swagger на /docs)
uvicorn app.main:app --reload

# 5. Фронтенд (отдельный терминал)
cd frontend && npm install && npm run dev
```

По умолчанию `APP_ENV=development` — проверки безопасности отключены. Для
прод-конфигурации см. `docs/security-checklist.md` (валидатор в `app/config.py`
не даст стартовать с небезопасными дефолтами при `APP_ENV=production`).

## Тесты и сборка

```bash
pytest -q                                    # бэкенд
cd frontend && npm run build                 # tsc + vite
APP_ENV=production python -c "from app.config import Settings; Settings()"  # упадёт при пустых секретах — это ожидаемо
```

## Деплой (self-hosted)

```bash
cp .env.production.example .env.production   # заполнить реальными значениями
docker compose --env-file .env.production up -d --build
docker compose run --rm backend alembic upgrade head
```

Подробности — в `docs/runbook.md` и `docs/deploy-selectel.md`.

## Шаблоны документов

`.docx`-шаблоны в `templates/` используют синтаксис **docxtpl** (Jinja2 внутри
Word). Стартовые шаблоны генерируются `scripts/generate_docx_templates.py`.

**Правило при правке в Word:** если меняете форматирование *внутри* плейсхолдера
`{{ … }}` — выделяйте плейсхолдер целиком. Иначе Word разрежет его на два
«run»-а, и движок перестанет его видеть (симптом: в готовом документе остаётся
`{{ contract_number }}` как текст).

| Синтаксис | Что делает |
|---|---|
| `{{ variable }}` | подставляет значение |
| `{% if x %}…{% endif %}` | условный кусок в строке |
| `{%p if x %}…{%p endif %}` | условный блок целых абзацев |
