#!/bin/bash
# Резервная копия базы uradres.net.
#
# Ставится в cron (см. deploy/setup-ops.sh). Логика простая намеренно: дамп,
# сжатие, выгрузка в тот же S3, где лежат файлы сервиса, ротация локальных
# копий. Чем меньше здесь движущихся частей, тем выше шанс, что бэкап
# действительно снимется в 4 утра без присмотра.
set -uo pipefail

PROJECT_DIR="${PROJECT_DIR:-/root/legal_address_service}"
BACKUP_DIR="${BACKUP_DIR:-/root/backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
LOG="${BACKUP_LOG:-/var/log/uradres-backup.log}"

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG"; }

cd "$PROJECT_DIR" || { log "FATAL: нет каталога $PROJECT_DIR"; exit 1; }

# Пользователь и база берутся из .env.production, а не задаются константой:
# роли `postgres` в этой инсталляции нет, и захардкоженное имя молча ломало бы
# бэкап каждую ночь.
PG_USER="$(grep -E '^POSTGRES_USER=' .env.production | head -1 | cut -d= -f2-)"
PG_DB="$(grep -E '^POSTGRES_DB=' .env.production | head -1 | cut -d= -f2-)"
if [ -z "$PG_USER" ] || [ -z "$PG_DB" ]; then
  log "FATAL: в .env.production нет POSTGRES_USER/POSTGRES_DB"
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="$BACKUP_DIR/${PG_DB}-$STAMP.sql.gz"

# --clean --if-exists: дамп можно накатить на существующую базу без ручной чистки.
if ! docker compose --env-file .env.production exec -T db \
      pg_dump -U "$PG_USER" --clean --if-exists "$PG_DB" 2>>"$LOG" | gzip -9 > "$FILE"; then
  log "FATAL: pg_dump упал"
  rm -f "$FILE"
  exit 1
fi

SIZE=$(stat -c%s "$FILE" 2>/dev/null || echo 0)
# Пустой или подозрительно маленький дамп — это тоже провал, просто тихий.
if [ "$SIZE" -lt 10240 ]; then
  log "FATAL: дамп $FILE подозрительно мал ($SIZE байт)"
  exit 1
fi
log "OK: $FILE ($((SIZE / 1024)) КБ)"

# Выгрузка в объектное хранилище: диск сервера — единая точка отказа.
#
# AWS_CA_BUNDLE обязателен: aws-cli v2 носит собственный набор корневых
# сертификатов и цепочку S3 Selectel не принимает («self-signed certificate in
# certificate chain»), хотя системному хранилищу она подходит.
if [ -n "${S3_BUCKET:-}" ] && command -v aws >/dev/null 2>&1; then
  export AWS_CA_BUNDLE="${AWS_CA_BUNDLE:-/etc/ssl/certs/ca-certificates.crt}"
  if aws --endpoint-url "${S3_ENDPOINT}" s3 cp "$FILE" "s3://${S3_BUCKET}/backups/$(basename "$FILE")" >>"$LOG" 2>&1; then
    log "OK: выгружено в s3://${S3_BUCKET}/backups/"
  else
    log "WARN: выгрузка в S3 не удалась — локальная копия осталась"
  fi
fi

# Ротация локальных копий.
DELETED=$(find "$BACKUP_DIR" -name "${PG_DB}-*.sql.gz" -mtime "+$KEEP_DAYS" -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && log "ротация: удалено $DELETED старых копий"

exit 0
