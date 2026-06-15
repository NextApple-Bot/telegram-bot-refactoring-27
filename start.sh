#!/bin/bash
set -euo pipefail

echo "🔥 Проверяем окружение..."
if [ -z "${DATABASE_URL:-}" ]; then
    echo "❌ FATAL: DATABASE_URL is not set!"
    exit 1
fi
if [ -z "${BOT_TOKEN:-}" ]; then
    echo "❌ FATAL: BOT_TOKEN is not set!"
    exit 1
fi
echo "✅ Переменные окружения в порядке."

export PYTHONPATH=/app
PORT=${PORT:-8000}
echo "Сервер будет слушать порт: $PORT"

echo ""
echo "🔄 Alembic current:"
alembic current

echo ""
echo "🔄 Применяем миграции Alembic..."
alembic upgrade head

echo ""
echo "✅ Миграции успешно применены."
echo "🔄 Текущая ревизия:"
alembic current

echo ""
echo "🚀 Запускаем основной сервер..."
exec python main.py
