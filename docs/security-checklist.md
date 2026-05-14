# Production security checklist

Этот чек-лист — короткий контракт между разработкой и деплоем. Если в `APP_ENV=production`
не выставлены значения ниже, сервис **откажется стартовать** (см. валидатор
`_enforce_production_hardening` в `app/config.py`). В `staging` валидатор тоже
работает, но можно временно понизить до `development`, чтобы выкатить пробу.

## Обязательно перед релизом

| Переменная | Значение для prod | Зачем |
|---|---|---|
| `APP_ENV` | `production` | Включает hardening-валидатор. |
| `SESSION_COOKIE_SECURE` | `true` | Без HTTPS-only куки токен сессии уйдёт по HTTP-сниффу. |
| `SESSION_COOKIE_SAMESITE` | `lax` или `strict` | `none` без `secure` запрещён. `strict` ломает редирект-логин по внешним ссылкам, `lax` — компромисс. |
| `SESSION_COOKIE_DOMAIN` | `.your-domain.tld` | Иначе кука не разделится между поддоменами (api / app). |
| `PAYMENT_WEBHOOK_SECRET` | сильный random ≥32 байт | Без секрета любой POST на `/api/v1/webhooks/*` подделает оплату. Должен совпадать с тем, что выдан провайдером. |
| `DATABASE_URL` | prod-кластер с least-priv ролью | Не используем суперюзера. Отдельная роль с правами только на нужную БД. |
| `STORAGE_BACKEND` | `s3` | LocalObjectStorage не покрывает контент-Type, версионирование, lifecycle. Выкладывать через nginx → утечка по path-traversal. |
| `S3_*` | прод-бакет + IAM-ключи | Бакет приватный, presigned URL по политике. |
| `DADATA_TOKEN` / `DADATA_SECRET` | боевые ключи | Иначе апдейт клиентов умрёт в 503. |
| `VAPID_*` | реальная пара | Иначе push выключен (но `enabled: false` это контролирует, поэтому не запрещаем). `VAPID_SUBJECT` должен быть реальный mailto/https. |
| `DB_ECHO` | пусто/`false` | Утекут запросы (PII) в stdout. |

## Сильно желательно

- **CDEK_***: продакшен URL `https://secure.cdekfin.ru`, `cdek_currency=RUR` (для TST это тест-валюта).
- **Reverse proxy** (nginx/Caddy) перед uvicorn: TLS-терминация, HSTS, rate-limit на `/auth/login`, `/marketplace/applications`, `/chats/*/messages`, `/push/subscribe`.
- **CORS**: на проде убедиться, что фронт и API на одном origin (cookie session работает без CORS-issue). Если разные домены — отдельная настройка `Allow-Origin`/`Allow-Credentials`.
- **Метрики**: `prometheus_fastapi_instrumentator` или эквивалент, дашборд по `4xx/5xx`, `latency p95`, RPS на чат-WS.
- **Логирование**: structured JSON (loguru/structlog), level `INFO`. ID запроса в каждой записи.
- **Sentry/Errortracker**: ловить непойманные исключения.
- **БД**: миграции `alembic upgrade head` идут в отдельный шаг pipeline, **до** деплоя кода (иначе старый код наткнётся на новую схему).
- **Backup**: postgres базовый бэкап + WAL-shipping. Тест restore раз в месяц.
- **Хранилище фото и счетов**: бакет приватный, отдача через presigned URL или прокси с auth-проверкой (см. `address-photos/{id}/raw`).
- **Avenue для приватных данных в логи**: маскировать `Authorization`, `password`, `token`, `vapid_private_pem`, cookies. ⚠ `email_outbox.send_email` пишет тело письма в логи — в проде заменить на реальный SMTP-провайдер.

## Веб

- HTTP-заголовки на nginx:
  - `Strict-Transport-Security: max-age=15552000; includeSubDomains; preload`
  - `Content-Security-Policy` — минимум `default-src 'self'; img-src 'self' data: https:; connect-src 'self' wss:`
  - `X-Frame-Options: DENY`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- Service Worker (`/sw.js`) обязательно отдаётся с правильным `Content-Type: application/javascript` без кеша.
- Vite-сборка прода: `npm run build`, отдача `dist/` через nginx (no fallback HTML index'а на API path).

## Тесты, которые нужно прогнать

```bash
.venv/bin/python -m pytest                  # 265+ зелёных
cd frontend && npm run build                # tsc + vite ok
APP_ENV=production .venv/bin/python -c "from app.config import settings"   # упадёт, если что-то забыли
```

## Источники проблем, замеченные у нас

- **Чат**: ws-эндпоинт без rate-limit'а. Под нагрузкой можно DOS'ить hub. → Добавить limit per user/min.
- **Email-stub**: пишет тело сообщения в логи. → Заменить на провайдера до выкатки.
- **Авто-модерация чата отложена** — фильтр оскорблений и контактов сейчас отсутствует. Включить до публичного запуска.
- **`session_cookie_secure=False`** — закрыто этим чек-листом: стартует только при `APP_ENV != production`.
