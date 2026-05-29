#!/usr/bin/env python3
"""
Скрипт для проверки здоровья сервиса.
Используется в Docker HEALTHCHECK и Render.
"""
import asyncio
import os
import sys

# Добавляем корень проекта в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.db import check_db_health, check_redis_health


async def main() -> int:
    """
    Возвращает 0, если все проверки пройдены, иначе 1.
    """
    db_ok = await check_db_health()
    if not db_ok:
        print("❌ Database is unhealthy", file=sys.stderr)
        return 1

    redis_ok = await check_redis_health()
    if not redis_ok:
        print("❌ Redis is unhealthy", file=sys.stderr)
        return 1

    print("✅ All services are healthy")
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
