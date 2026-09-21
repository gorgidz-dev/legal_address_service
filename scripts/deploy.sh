#!/usr/bin/env bash
# Идемпотентный деплой прод-стека (Caddy + frontend + backend + postgres).
# Запуск на сервере из корня репозитория:  bash scripts/deploy.sh
#
# Делает:
#   1. Проверяет .env.production.
#   2. Автогенерит POSTGRES_PASSWORD и PAYMENT_WEBHOOK_SECRET, если плейсхолдеры.
#   3. Проверяет, что внешние секреты (DaData / S3 / Yandex) заполнены.
#   4. Собирает образы и прогоняет миграции НОВЫМ образом — до переключения
#      контейнеров; затем up и ждёт health бэка.
set -euo pipefail

cd "$(dirname "$0")/.."
ENV=.env.production
COMPOSE="docker compose --env-file $ENV"

if [ ! -f "$ENV" ]; then
  echo "✗ Нет $ENV"
  echo "  cp .env.production.example .env.production  и заполни секреты."
  exit 1
fi

# --- 1. Автогенерация локальных секретов, если ещё плейсхолдеры (__...__) ---
gen_if_placeholder() {
  local key="$1" gencmd="$2" cur
  cur="$(grep -E "^${key}=" "$ENV" | head -1 | cut -d= -f2-)"
  if printf '%s' "$cur" | grep -q '__'; then
    local val
    val="$($gencmd)"
    sed -i.bak "s|^${key}=.*|${key}=${val}|" "$ENV"
    rm -f "${ENV}.bak"
    echo "  ✓ сгенерирован ${key}"
  fi
}
gen_if_placeholder POSTGRES_PASSWORD       "openssl rand -hex 24"
gen_if_placeholder PAYMENT_WEBHOOK_SECRET  "openssl rand -hex 32"

# --- 2. Проверка внешних секретов (их можешь дать только ты) ---
missing=0
for k in DADATA_TOKEN DADATA_SECRET S3_ACCESS_KEY S3_SECRET_KEY VITE_YANDEX_MAPS_KEY; do
  v="$(grep -E "^${k}=" "$ENV" | head -1 | cut -d= -f2-)"
  if [ -z "$v" ] || printf '%s' "$v" | grep -q '__'; then
    echo "  ✗ заполни ${k} в ${ENV}"
    missing=1
  fi
done
if [ "$missing" -ne 0 ]; then
  echo "Заполни недостающие секреты и запусти снова."
  exit 1
fi

# --- 3. Сборка, миграции, запуск ---
# Миграции — ДО переключения контейнеров. Иначе новый код стартует раньше
# схемы: ORM читает колонки, которых ещё нет, и все запросы к изменённым
# таблицам падают UndefinedColumn, пока миграция не догонит (найдено ревизией
# при добавлении колонок платежей Т-Банка). Работает, пока миграции аддитивные
# (новые колонки nullable/с умолчанием): старый код их не замечает. Удалять и
# переименовывать колонки — в два деплоя (сначала код перестаёт их читать).
echo "==> docker compose build"
$COMPOSE build

echo "==> alembic upgrade head (новым образом, до переключения)"
$COMPOSE run --rm backend alembic upgrade head

echo "==> docker compose up"
$COMPOSE up -d

# --- 4. Ждём health бэкенда ---
echo "==> жду backend /health"
ok=0
for _ in $(seq 1 60); do
  if $COMPOSE exec -T backend curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
    ok=1; echo "  ✓ backend healthy"; break
  fi
  sleep 3
done
if [ "$ok" -ne 1 ]; then
  echo "✗ backend не поднялся. Логи:  $COMPOSE logs backend"
  exit 1
fi

echo
echo "==> статус"
$COMPOSE ps
echo
echo "Готово."
echo "  https://uradres.net  → «Первый вход» создаст первого админа."
echo "  Сертификат Caddy:  $COMPOSE logs caddy | grep -i certificate"
