#!/bin/bash
# Внешняя проверка живости uradres.net с уведомлением в Telegram.
#
# Запускается по cron раз в 5 минут. Смысл — узнать о падении раньше клиента.
#
# Уведомляем по фронту состояния: одно сообщение при падении и одно при
# восстановлении. Иначе ночной сбой превращается в 100 одинаковых сообщений,
# и на них перестают смотреть.
set -uo pipefail

URL="${HEALTH_URL:-https://uradres.net/health}"
CATALOG_URL="${CATALOG_URL:-https://uradres.net/api/v1/marketplace/addresses/search?page_size=1}"
STATE_FILE="${HEALTH_STATE:-/var/lib/uradres-health.state}"
LOG="${HEALTH_LOG:-/var/log/uradres-health.log}"
TIMEOUT="${HEALTH_TIMEOUT:-20}"

# Заполняется в deploy/setup-ops.sh
TG_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
TG_CHAT="${TELEGRAM_CHAT_ID:-}"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

notify() {
  [ -z "$TG_TOKEN" ] || [ -z "$TG_CHAT" ] && return 0
  curl -s -m 15 -o /dev/null \
    --data-urlencode "chat_id=${TG_CHAT}" \
    --data-urlencode "text=$1" \
    "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" || true
}

check() {
  local url="$1" expected="$2"
  local code
  code=$(curl -s -m "$TIMEOUT" -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo 000)
  [ "$code" = "$expected" ]
}

FAILURES=""
check "$URL" 200 || FAILURES="${FAILURES}health "
check "$CATALOG_URL" 200 || FAILURES="${FAILURES}каталог "

# Срок действия TLS-сертификата: Caddy продлевает сам, но если продление
# сломается, узнать об этом лучше заранее, а не в день истечения.
DOMAIN=$(echo "$URL" | sed -E 's#https?://([^/]+).*#\1#')
EXPIRY=$(echo | openssl s_client -connect "${DOMAIN}:443" -servername "$DOMAIN" 2>/dev/null \
  | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2)
if [ -n "$EXPIRY" ]; then
  LEFT=$(( ( $(date -d "$EXPIRY" +%s) - $(date +%s) ) / 86400 ))
  [ "$LEFT" -lt 10 ] && FAILURES="${FAILURES}TLS(${LEFT}д) "
fi

PREV=$(cat "$STATE_FILE" 2>/dev/null || echo "ok")

if [ -n "$FAILURES" ]; then
  log "DOWN: $FAILURES"
  if [ "$PREV" != "down" ]; then
    notify "🔴 uradres.net: проблема — ${FAILURES}"
    echo "down" > "$STATE_FILE"
  fi
  exit 1
fi

log "OK"
if [ "$PREV" = "down" ]; then
  notify "🟢 uradres.net: восстановлено"
fi
echo "ok" > "$STATE_FILE"
exit 0
