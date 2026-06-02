#!/bin/bash
set -e

echo "🔄 Запуск резервного копирования PostgreSQL..."

if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL не задан"
    exit 1
fi

BACKUP_DIR="/app/backups"
mkdir -p "$BACKUP_DIR"

DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.sql.gz"

echo "📦 Создаём дамп..."
pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"
echo "✅ Дамп сохранён: $BACKUP_FILE"

# === Опциональная загрузка в облако ===

# S3 / совместимое хранилище
if [ -n "$S3_BUCKET" ]; then
    echo "☁️ Загрузка в S3..."
    aws s3 cp "$BACKUP_FILE" "s3://$S3_BUCKET/backups/" || true
fi

# rclone (Google Drive / Yandex / etc)
if [ -n "$RCLONE_REMOTE" ]; then
    echo "☁️ Загрузка через rclone..."
    rclone copy "$BACKUP_FILE" "$RCLONE_REMOTE:backups/" || true
fi

# Очистка старых локальных бэкапов (старше 7 дней)
find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +7 -delete 2>/dev/null || true

echo "✅ Резервное копирование завершено"
