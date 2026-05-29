#!/bin/sh
set -e

echo "🔥 Проверяем окружение..."
if [ -z "$DATABASE_URL" ]; then
    echo "❌ FATAL: DATABASE_URL is not set!"
    exit 1
fi

if [ -z "$BOT_TOKEN" ]; then
    echo "❌ FATAL: BOT_TOKEN is not set!"
    exit 1
fi

echo "✅ Переменные окружения в порядке."

export PYTHONPATH=/app

# Покажем, какой порт будет использован (для диагностики)
echo "Сервер будет слушать порт: ${PORT:-8000}"

echo "🔄 Применяем миграции Alembic..."
alembic upgrade head || echo "⚠️ Миграции не выполнены (возможно уже актуальны)"

echo "🚀 Запускаем основной сервер..."
exec python main.py
