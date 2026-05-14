# Runbook — запуск, demo data, smoke-проверка, откат

Один короткий документ. Без архитектурных деталей. Только команды и зачем.
Подробности безопасности — `docs/security-checklist.md`.

## 0. Предусловия

- Python 3.11+ (`python3 --version`)
- Node 20+ (`node --version`)
- PostgreSQL 14+ (или MinIO для S3 — опционально)
- LibreOffice (`libreoffice --version`) — нужен только для генерации PDF из docx

```bash
git clone <repo> legal_address_service && cd legal_address_service
cp .env.example .env        # потом отредактировать
```

Минимум в `.env` для локалки:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/legal_address
APP_ENV=development
STORAGE_BACKEND=local
```
DaData/CDEK/VAPID можно оставить пустыми — соответствующие фичи вернут 503,
основные потоки не сломаются.

## 1. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

createdb legal_address                # один раз
.venv/bin/alembic upgrade head        # применить все миграции

.venv/bin/uvicorn app.main:app --reload --port 8000
```
API на `http://127.0.0.1:8000`, Swagger — `http://127.0.0.1:8000/docs`.

### Когда переcоздавать БД

```bash
dropdb legal_address && createdb legal_address && .venv/bin/alembic upgrade head
```
Делать только локально. На staging/prod — миграции, не drop.

### Тесты

```bash
.venv/bin/python -m pytest                # должно быть 272+ зелёных
.venv/bin/python -m pytest -k chat        # точечно
```

## 2. Frontend

```bash
cd frontend
npm install
npm run dev                  # http://127.0.0.1:5173
```
Vite проксирует `/api`, `/auth`, `/push`, `/sw.js` на `127.0.0.1:8000` (см. `vite.config.ts`).

Прод-сборка:
```bash
npm run build                # dist/ — отдаётся nginx'ом
npm run preview              # проверить локально
```

## 3. Demo data

Два сидера, идемпотентные, можно гонять подряд.

```bash
# Юзеры (admin/owner-msk/owner-spb/client) + заявки в маркетплейс.
.venv/bin/python -m scripts.seed_marketplace_demo

# Адреса с фото и сервисами (через Pillow — генерит градиенты).
.venv/bin/python -m scripts.seed_demo_addresses
```

Все демо-аккаунты — пароль **`demo12345`**:

| Роль | Email |
|---|---|
| admin | `admin@uradres-demo.ru` |
| owner (Москва) | `owner-msk@uradres-demo.ru` |
| owner (СПб) | `owner-spb@uradres-demo.ru` |
| client | `client@uradres-demo.ru` |

## 4. Smoke-проверка перед коммитом / релизом

```bash
# 1) Backend стартует с правильным env-валидатором:
.venv/bin/python -c "from app.config import settings; print(settings.app_env)"

# 2) Прод-валидатор реально работает (должно упасть с перечислением):
APP_ENV=production .venv/bin/python -c "from app.config import Settings; Settings()"

# 3) Тесты:
.venv/bin/python -m pytest

# 4) Frontend tsc + vite:
cd frontend && npm run build && cd ..
```

### Ручные потоки (после `seed_marketplace_demo`)

1. **Логин client** → marketplace → выбрать адрес → создать заявку → видим её в кабинете.
2. **Логин owner** → видит свежую заявку → принять → чат открывается с обеих сторон.
3. **Чат**: 2-3 сообщения, проверить что у второго юзера приходит push (если VAPID настроен — иначе игнор).
4. **Логин admin** → видит payments / applications / providers.
5. **Push toggle**: в client-кабинете — `Включить уведомления` → `granted-subscribed`. Отписаться → исчезает.

## 5. S3 / MinIO (опционально)

Локально по дефолту `STORAGE_BACKEND=local` — файлы лежат в `storage/`. Этого
хватает для разработки. S3 нужен для prod (см. `docs/security-checklist.md`).

### MinIO в Docker для локальной отладки S3-режима

```bash
docker run -d --name minio \
  -p 9000:9000 -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  -v minio-data:/data \
  minio/minio server /data --console-address ":9001"
```

Веб-консоль — `http://127.0.0.1:9001` (логин `minioadmin` / `minioadmin`).
Создать бакет `legal-address` через UI или CLI:

```bash
docker run --rm --network host minio/mc \
  alias set local http://127.0.0.1:9000 minioadmin minioadmin && \
docker run --rm --network host minio/mc mb local/legal-address
```

В `.env`:
```
STORAGE_BACKEND=s3
S3_ENDPOINT=http://127.0.0.1:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=legal-address
S3_REGION=ru-central1
```

Проверка:
```bash
.venv/bin/python -c "from app.services.storage import get_object_storage; s = get_object_storage(); print(s.backend)"
# должно вывести: s3
```

Если получаешь `RuntimeError: Для STORAGE_BACKEND=s3 нужны S3_ACCESS_KEY...` —
не подцепился `.env` (uvicorn перезапустить после правки) или ключи пустые.

### Yandex Object Storage (прод-вариант)

В консоли YC:
1. Создать сервисный аккаунт с ролью `storage.editor`.
2. Создать статический ключ доступа (получишь `KEY_ID` + `SECRET`).
3. Создать приватный бакет (acl=private, шифрование включить).

```
STORAGE_BACKEND=s3
S3_ENDPOINT=https://storage.yandexcloud.net
S3_ACCESS_KEY=<KEY_ID>
S3_SECRET_KEY=<SECRET>
S3_BUCKET=<bucket-name>
S3_REGION=ru-central1
```

Приватные файлы (фото адресов, счета) отдавать не публичным URL'ом, а через
наш бэк с auth-проверкой — см. эндпоинт `address-photos/{id}/raw` как образец.

### Миграция данных local → s3

Готового скрипта нет. Простой путь — `mc mirror`:
```bash
docker run --rm --network host -v $(pwd)/storage:/local minio/mc \
  mirror /local local/legal-address
```
После этого `STORAGE_BACKEND=s3` и рестарт.

⚠ В БД пути в `storage_key` относительные, поэтому ничего перешивать не нужно.
Но если ключи в `storage/` лежали с подпапками (`address-photos/...`) — структура
должна сохраниться в бакете 1:1.

## 6. Откат после неудачного релиза

### Код

```bash
git log --oneline -n 10            # найти последний хороший коммит
git revert <bad-sha>               # создаёт обратный коммит (предпочтительно)
# или, если ещё не запушено:
git reset --hard <good-sha>        # ⚠ деструктив, осторожно
git push                           # обычный push, БЕЗ --force на main
```
`--force` на main — только если знаешь, что делаешь, и предупредил команду.

### Миграции

Откатываются по одной. Сначала смотрим текущую:
```bash
.venv/bin/alembic current
.venv/bin/alembic history | head -20
```

Откатить на одну ступень:
```bash
.venv/bin/alembic downgrade -1
```

Откатить до конкретной (ID берётся из имени файла `versions/..._XXXX_*.py`):
```bash
.venv/bin/alembic downgrade 0019
```

Если миграция уже сделала `DROP COLUMN` с данными — данные не вернутся.
Перед опасными миграциями: `pg_dump legal_address > backup.sql` ДО `upgrade head`.

### Полный rollback пайплайна (если деплой пошёл криво)

1. `kubectl rollout undo deploy/api` (или эквивалент в твоей оркестрации).
2. `alembic downgrade <prev-rev>` — только если новая миграция несовместима со старым кодом.
3. Сбросить кеш CDN/nginx для `/sw.js` (Service Worker может закэшироваться у клиентов).
4. Постмортем в `docs/handoff/` — что упало, что вернули.

## 7. Что почитать дальше

- `docs/security-checklist.md` — обязательные env-переменные для prod.
- `docs/mobile-api.md` — endpoint'ы для мобилки.
- `README.md` — устарел в части слоя БД и шаблонов, но описание плейсхолдеров (`{{ }}`, `{% %}`, `{%p %}`) актуально.
