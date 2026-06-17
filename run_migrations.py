#!/usr/bin/env python3
"""
Улучшенный скрипт применения миграций с проверками.
"""

import asyncio
import logging
import os
import sys

from alembic.config import Config
from alembic import command

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def run_migrations():
    logger.info("🔄 Применяем миграции Alembic...")

    alembic_cfg = Config("alembic.ini")

    try:
        # Сначала проверяем текущее состояние
        from scripts.check_migrations import check_migrations
        if not await check_migrations():
            logger.error("❌ Проверка миграций не прошла. Прерываем.")
            sys.exit(1)

        # Применяем миграции
        command.upgrade(alembic_cfg, "head")
        logger.info("✅ Все миграции успешно применены!")

        # Показываем текущую ревизию
        command.current(alembic_cfg)

    except Exception as e:
        logger.error(f"❌ Ошибка при применении миграций: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(run_migrations())
