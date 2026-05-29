#!/bin/sh
set -e

echo "🚀 Запуск Telegram Bot + Admin Panel..."

# Применяем миграции
echo "📦 Применяем Alembic миграции..."
python run_migrations.py

# Проверка здоровья БД (опционально)
echo "🔍 Проверка подключения к базе..."
python -c "
from bot.db import check_db_health
import asyncio
print('✅ БД доступна' if asyncio.run(check_db_health()) else '❌ Проблема с БД')
"

echo "🌐 Запуск uvicorn сервера..."
exec uvicorn main:main_entry \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers 2 \
    --log-level info
