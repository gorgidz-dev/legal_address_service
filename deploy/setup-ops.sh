#!/bin/bash
# Установка эксплуатационной обвязки на сервере: бэкапы БД + внешний
# healthcheck с уведомлением в Telegram.
#
# Запускать на сервере из каталога проекта:
#   bash deploy/setup-ops.sh
#
# Скрипт идемпотентный: повторный запуск ничего не ломает.
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-/root/legal_address_service}"
cd "$PROJECT_DIR"

echo "=== 1. Каталоги и права ==="
mkdir -p /root/backups /var/lib
touch /var/log/uradres-backup.log /var/log/uradres-health.log
chmod 700 /root/backups
install -m 700 deploy/backup-db.sh /root/backup-db.sh
install -m 700 deploy/healthcheck.sh /root/healthcheck.sh
echo "  скрипты установлены в /root"

echo
echo "=== 2. Конфиг эксплуатации (/root/ops.env) ==="
if [ ! -f /root/ops.env ]; then
  # S3-реквизиты берём из уже настроенного .env.production, чтобы не заводить
  # второй источник правды.
  {
    echo "# Заполните TELEGRAM_*, чтобы приходили уведомления о падении."
    echo "TELEGRAM_BOT_TOKEN="
    echo "TELEGRAM_CHAT_ID="
    grep -E '^(S3_ENDPOINT|S3_BUCKET|S3_ACCESS_KEY|S3_SECRET_KEY)=' .env.production || true
  } > /root/ops.env
  chmod 600 /root/ops.env
  echo "  создан /root/ops.env — впишите TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID"
else
  echo "  /root/ops.env уже есть, не трогаю"
fi

echo
echo "=== 3. aws-cli для выгрузки бэкапов в S3 ==="
if command -v aws >/dev/null 2>&1; then
  echo "  уже установлен: $(aws --version 2>&1 | head -1)"
else
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq >/dev/null 2>&1 || true
  apt-get install -y -qq awscli >/dev/null 2>&1 && echo "  установлен" || \
    echo "  ПРЕДУПРЕЖДЕНИЕ: не поставился, бэкапы останутся только локально"
fi

# Профиль для S3-совместимого хранилища Selectel.
if [ -n "$(grep -E '^S3_ACCESS_KEY=' /root/ops.env | cut -d= -f2-)" ]; then
  mkdir -p /root/.aws
  {
    echo "[default]"
    echo "aws_access_key_id = $(grep -E '^S3_ACCESS_KEY=' /root/ops.env | cut -d= -f2-)"
    echo "aws_secret_access_key = $(grep -E '^S3_SECRET_KEY=' /root/ops.env | cut -d= -f2-)"
  } > /root/.aws/credentials
  chmod 600 /root/.aws/credentials
  echo "  учётные данные S3 записаны"
fi

echo
echo "=== 4. Задания cron ==="
# Собираем crontab заново из «своих» строк, чтобы повторный запуск не плодил дубли.
CRON_TMP=$(mktemp)
crontab -l 2>/dev/null \
  | grep -v 'backup-db.sh\|healthcheck.sh\|send_stage_deadline_reminders\|send_contract_expiry_reminders' \
  > "$CRON_TMP" || true
# Рассылки идут через exec в работающий контейнер, а не через `compose run`:
# run поднимает новый контейнер на каждый запуск, а это ежедневная задача.
# Если бэкенд лежит — задание просто не отработает, и это правильно.
cat >> "$CRON_TMP" <<'CRON'
# uradres: резервная копия БД каждую ночь в 04:15
15 4 * * * set -a; . /root/ops.env; set +a; /root/backup-db.sh
# uradres: проверка живости каждые 5 минут
*/5 * * * * set -a; . /root/ops.env; set +a; /root/healthcheck.sh
# uradres: напоминания по внутренним срокам этапов — 09:10 МСК (сервер в UTC).
# Дедлайн ставится на 18:00 МСК, поэтому «сегодня последний день» приходит утром
# того же дня, а не после его окончания.
10 6 * * * cd /root/legal_address_service && docker compose --env-file .env.production exec -T backend python -m scripts.send_stage_deadline_reminders >> /var/log/uradres-reminders.log 2>&1
# uradres: напоминания клиентам об истекающих договорах — 09:20 МСК
20 6 * * * cd /root/legal_address_service && docker compose --env-file .env.production exec -T backend python -m scripts.send_contract_expiry_reminders >> /var/log/uradres-reminders.log 2>&1
CRON
crontab "$CRON_TMP"
rm -f "$CRON_TMP"
crontab -l | grep -E 'backup-db|healthcheck|reminders'

echo
echo "=== 5. Контрольный прогон бэкапа ==="
set -a; . /root/ops.env; set +a
if /root/backup-db.sh; then
  ls -lh /root/backups | tail -3
else
  echo "  БЭКАП НЕ СНЯЛСЯ — смотрите /var/log/uradres-backup.log"
fi

echo
echo "=== 6. Контрольный прогон healthcheck ==="
set -a; . /root/ops.env; set +a
/root/healthcheck.sh && echo "  сервис отвечает" || echo "  healthcheck сообщил о проблеме"

echo
echo "OPS_SETUP_DONE"
