#!/bin/bash
set -e

# ============================================================
# Автоматическое резервное копирование PostgreSQL
# Запускается через Render Cron Job или вручную
# ============================================================

echo "🔄 Запуск резервного копирования..."

# Проверяем наличие DATABASE_URL
if [ -z "$DATABASE_URL" ]; then
    echo "❌ DATABASE_URL не задан. Бекап невозможен."
    exit 1
fi

# Определяем имя файла с датой
BACKUP_DIR="/app/backups"
mkdir -p "$BACKUP_DIR"
DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="$BACKUP_DIR/backup_$DATE.sql.gz"

# Создаём дамп и сжимаем
echo "📦 Создание дампа базы данных..."
pg_dump "$DATABASE_URL" | gzip > "$BACKUP_FILE"
echo "✅ Дамп сохранён: $BACKUP_FILE"

# --- ЗАГРУЗКА В ОБЛАКО (если настроены переменные) ---

# Вариант 1: AWS S3 (или совместимое хранилище)
if [ -n "$S3_BUCKET" ] && [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then
    echo "☁️ Загрузка в S3..."
    # Установка AWS CLI, если ещё нет (для Render можно предустановить)
    if ! command -v aws &> /dev/null; then
        pip install awscli
    fi
    aws s3 cp "$BACKUP_FILE" "s3://$S3_BUCKET/backups/$DATE.sql.gz" --endpoint-url "$S3_ENDPOINT" 2>/dev/null || \
    aws s3 cp "$BACKUP_FILE" "s3://$S3_BUCKET/backups/$DATE.sql.gz"
    echo "✅ Загружено в S3"
fi

# Вариант 2: Google Drive через rclone
if [ -n "$RCLONE_CONFIG" ] && [ -n "$RCLONE_REMOTE" ]; then
    echo "☁️ Загрузка в Google Drive..."
    if ! command -v rclone &> /dev/null; then
        curl https://rclone.org/install.sh | bash
    fi
    echo "$RCLONE_CONFIG" > /tmp/rclone.conf
    rclone --config /tmp/rclone.conf copy "$BACKUP_FILE" "$RCLONE_REMOTE/backups/"
    rm -f /tmp/rclone.conf
    echo "✅ Загружено в Google Drive"
fi

# Удаляем локальные бекапы старше 7 дней (если не загружаем в облако)
if [ -z "$S3_BUCKET" ] && [ -z "$RCLONE_REMOTE" ]; then
    find "$BACKUP_DIR" -name "backup_*.sql.gz" -mtime +7 -delete
    echo "🧹 Локальные бекапы старше 7 дней удалены"
else
    # Если загружаем в облако, удаляем все локальные файлы сразу после загрузки
    rm -f "$BACKUP_DIR"/*.sql.gz
    echo "🧹 Локальные бекапы удалены после загрузки в облако"
fi

echo "✅ Резервное копирование завершено"
