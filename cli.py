#!/usr/bin/env python
"""
CLI утилита для управления ботом (миграции, очистка и т.д.).
"""

import asyncio
import logging
import os
import subprocess
import sys
from pathlib import Path

# Добавляем корень проекта
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

from bot.background import cleanup_old_records, cleanup_sold_periodically
from bot.db import dispose_engine

load_dotenv()
logger = logging.getLogger(__name__)


def run_migrations():
    """Запускает Alembic миграции."""
    if not os.getenv("DATABASE_URL"):
        print("❌ DATABASE_URL не задан в .env")
        sys.exit(1)

    print("🔄 Применяем миграции...")
    try:
        result = subprocess.run(["alembic", "upgrade", "head"], check=True)
        print("✅ Миграции успешно применены.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка миграций: {e}")
        sys.exit(1)


async def run_cleanup_async():
    """Асинхронная очистка."""
    print("🔄 Запуск очистки старых записей...")
    await cleanup_old_records()

    print("🔄 Запуск очистки проданных товаров...")
    await cleanup_sold_periodically()

    await dispose_engine()
    print("✅ Очистка завершена.")


def run_cleanup():
    asyncio.run(run_cleanup_async())


def show_help():
    print("Usage: python cli.py [command]")
    print("Commands:")
    print("  migrate   - Run database migrations")
    print("  cleanup   - Run cleanup of old records")
    print("  help      - Show this help")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_help()
        sys.exit(1)

    command = sys.argv[1].lower()
    if command == "migrate":
        run_migrations()
    elif command == "cleanup":
        run_cleanup()
    elif command in ("help", "--help", "-h"):
        show_help()
    else:
        print(f"❌ Неизвестная команда: {command}")
        show_help()
        sys.exit(1)
