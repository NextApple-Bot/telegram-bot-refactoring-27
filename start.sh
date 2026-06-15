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

echo "Сервер будет слушать порт: ${PORT:-8000}"

echo ""
echo "🔄 Текущая ревизия Alembic:"
alembic current || true

echo ""
echo "🔄 Применяем миграции Alembic (строго, с ошибкой при неудаче)..."
alembic upgrade head

echo ""
echo "✅ Миграции успешно применены."
echo "🔄 Новая ревизия Alembic:"
alembic current || true

echo ""
echo "🚀 Запускаем основной сервер..."
exec python main.py
