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

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
FILE="$BACKUP_DIR/legal_address-$STAMP.sql.gz"

# --clean --if-exists: дамп можно накатить на существующую базу без ручной чистки.
if ! docker compose --env-file .env.production exec -T db \
      pg_dump -U postgres --clean --if-exists legal_address 2>>"$LOG" | gzip -9 > "$FILE"; then
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
if [ -n "${S3_BUCKET:-}" ] && command -v aws >/dev/null 2>&1; then
  if aws --endpoint-url "${S3_ENDPOINT}" s3 cp "$FILE" "s3://${S3_BUCKET}/backups/$(basename "$FILE")" >>"$LOG" 2>&1; then
    log "OK: выгружено в s3://${S3_BUCKET}/backups/"
  else
    log "WARN: выгрузка в S3 не удалась — локальная копия осталась"
  fi
fi

# Ротация локальных копий.
DELETED=$(find "$BACKUP_DIR" -name 'legal_address-*.sql.gz' -mtime "+$KEEP_DAYS" -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && log "ротация: удалено $DELETED старых копий"

exit 0
