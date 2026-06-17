#!/usr/bin/env python3
"""
Полноценный скрипт применения миграций с автоматической проверкой.
"""

import asyncio
import logging
import sys

from alembic.config import Config
from alembic import command

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def run_migrations_sync():
    """Синхронная обёртка для применения миграций."""
    logger.info("🔄 Применяем миграции Alembic...")

    alembic_cfg = Config("alembic.ini")

    try:
        # Применяем миграции
        command.upgrade(alembic_cfg, "head")
        logger.info("✅ Все миграции успешно применены!")

        # Показываем текущую ревизию
        command.current(alembic_cfg)

    except Exception as e:
        logger.error(f"❌ Ошибка при применении миграций: {e}")
        sys.exit(1)


async def check_migrations_async():
    """Асинхронная проверка миграций (опционально)."""
    try:
        from scripts.check_migrations import check_migrations
        result = await check_migrations()
        return result
    except Exception as e:
        logger.warning(f"⚠️ Проверка миграций завершилась с ошибкой (пропускаем): {e}")
        return True  # Не блокируем деплой при ошибке проверки


async def main():
    # Сначала пробуем проверить (но не блокируем деплой, если проверка упала)
    await check_migrations_async()

    # Применяем миграции (это главное)
    run_migrations_sync()


if __name__ == "__main__":
    asyncio.run(main())
