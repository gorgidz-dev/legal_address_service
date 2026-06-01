# Деплой на Selectel (uradres.market)

Прод-стек: **Caddy → frontend (nginx+SPA) → backend (FastAPI) → PostgreSQL**,
файлы в **Selectel S3**. Платежи на старте — **вручную** (CDEK выключен).
TLS — авто-Let's Encrypt через Caddy.

Все команды выполняются на арендованном сервере Selectel (Ubuntu 22.04+).

---

## 0. Предусловия (один раз)

- [ ] SSH-доступ к серверу под пользователем с `sudo`.
- [ ] Домен `uradres.market` зарегистрирован.
- [ ] Аккаунт DaData с боевым токеном.
- [ ] Яндекс.Карты JS API key.

---

## 1. DNS — направить домен на сервер

В панели регистратора (или Selectel DNS, если делегирован) создать записи на
**публичный IP сервера**:

```
A    uradres.market       → <SERVER_IP>
A    www.uradres.market   → <SERVER_IP>
```

Проверить распространение (с локальной машины):

```bash
dig +short uradres.market
```

⚠️ Caddy не получит сертификат, пока A-запись не указывает на сервер и порты
80/443 не открыты. Делать ДО `up`.

---

## 2. Selectel S3 — контейнер для файлов

Панель Selectel → **Облачное хранилище**:

1. Создать контейнер `uradres-prod`.
   - Фото адресов показываются в каталоге → нужен **публичный доступ на чтение**
     (тип контейнера «публичный») ИЛИ оставить приватным и позже включить
     раздачу через presigned (см. «Дальнейшие шаги»). Для MVP — публичный.
2. Создать **сервисного пользователя S3** (Access Key + Secret Key).
3. Запомнить endpoint пула (обычно `https://s3.ru-1.storage.selcloud.ru`).

---

## 3. Сервер — базовая подготовка

```bash
# Docker + compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker        # применить группу без релогина

# Файрвол: только SSH + HTTP/HTTPS
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

---

## 4. Код + секреты

```bash
git clone https://github.com/<owner>/legal_address_service.git
cd legal_address_service

cp .env.production.example .env.production
nano .env.production        # заполнить ВСЕ __плейсхолдеры__
```

Сгенерировать секреты прямо на сервере:

```bash
# Webhook-секрет платёжки
openssl rand -hex 32

# Пароль БД
openssl rand -hex 24

# VAPID-пара для web-push
docker run --rm -v "$PWD":/app -w /app python:3.12-slim sh -c \
  "pip install -q -r requirements.txt && python scripts/gen_vapid_keys.py"
```

Минимальный чек по `.env.production` (см. `docs/security-checklist.md`):

| Переменная | Значение |
|---|---|
| `APP_ENV` | `production` |
| `POSTGRES_PASSWORD` | сгенерированный |
| `SESSION_COOKIE_SECURE` | `true` |
| `SESSION_COOKIE_DOMAIN` | `.uradres.market` |
| `PAYMENT_WEBHOOK_SECRET` | `openssl rand -hex 32` |
| `DADATA_TOKEN` / `DADATA_SECRET` | боевые |
| `STORAGE_BACKEND` | `s3` |
| `S3_*` | из шага 2 |
| `VAPID_*` | из генератора |
| `ACME_EMAIL` | реальный e-mail (для Let's Encrypt) |
| `VITE_YANDEX_MAPS_KEY` | JS API key |
| `CDEK_LOGIN` / `CDEK_SECRET_KEY` | **пусто** (платежи вручную) |

---

## 5. Запуск

```bash
# Сборка и старт всех сервисов
docker compose --env-file .env.production up -d --build

# Применить миграции БД (отдельным шагом, после старта db)
docker compose --env-file .env.production run --rm backend alembic upgrade head

# Создать первого админа / демо-данные (по желанию)
docker compose --env-file .env.production run --rm backend \
  python -m scripts.seed_marketplace_demo --password '__сильный_пароль__'
```

Caddy при первом старте сам получит сертификат для `uradres.market`
(может занять до минуты). Логи:

```bash
docker compose logs -f caddy
```

---

## 6. Проверка

```bash
# Health бэкенда через публичный домен
curl -fsS https://uradres.market/health

# Каталог отдаёт адреса
curl -fsS 'https://uradres.market/api/v1/marketplace/addresses/search?page=1&page_size=1'
```

В браузере: `https://uradres.market` — каталог, замок TLS, карта (если ключ задан).

---

## 7. Бэкап БД (cron)

```bash
# /etc/cron.daily/uradres-pgdump (chmod +x)
#!/bin/sh
cd /home/<user>/legal_address_service
docker compose --env-file .env.production exec -T db \
  pg_dump -U legal_address legal_address | gzip > \
  /var/backups/uradres-$(date +\%F).sql.gz
find /var/backups -name 'uradres-*.sql.gz' -mtime +14 -delete
```

Раз в месяц проверять restore на staging.

---

## Обновление (новый релиз)

```bash
cd legal_address_service
git pull
docker compose --env-file .env.production up -d --build
docker compose --env-file .env.production run --rm backend alembic upgrade head
```

---

## Дальнейшие шаги (после запуска)

- **SMTP**: заменить email-stub на реального провайдера (письма сейчас в логах).
- **CDEK Pay**: вписать боевые `CDEK_LOGIN` / `CDEK_SECRET_KEY` → авто-приём СБП.
- **Sentry**: добавить DSN для трекинга ошибок.
- **S3 presigned**: если контейнер приватный — раздача фото через presigned URL.
- **Авто-модерация чата**: фильтр контактов/оскорблений (см. security-checklist).
- **Rate-limit** на `/api/v1/auth/login` и чат-WS (на уровне Caddy или бэка).
