#!/usr/bin/env python3
"""
Автоматическая проверка миграций Alembic.
"""

import asyncio
import logging
import sys

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from bot.config import config as bot_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


async def check_migrations() -> bool:
    logger.info("🔍 Запуск проверки миграций...")

    DATABASE_URL = bot_config.DATABASE_URL

    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL не задан")
        return False

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    script = ScriptDirectory.from_config(alembic_cfg)

    engine = create_async_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
    )

    async with engine.connect() as conn:
        context = MigrationContext.configure(conn.sync_connection)
        current_rev = context.get_current_revision()

    head_rev = script.get_current_head()

    logger.info(f"Текущая ревизия в БД: {current_rev}")
    logger.info(f"Head ревизия:        {head_rev}")

    if current_rev != head_rev:
        logger.error("❌ Миграции не актуальны!")
        return False

    logger.info("✅ Ревизии совпадают")

    # Проверка таблиц из моделей
    try:
        from bot.models import Base
        async with engine.connect() as conn:
            inspector = inspect(conn.sync_connection)
            existing_tables = set(inspector.get_table_names())

            for table in Base.metadata.tables.keys():
                if table not in existing_tables:
                    logger.error(f"❌ Таблица '{table}' отсутствует в БД")
                    return False

        logger.info("✅ Все таблицы из моделей присутствуют в БД")
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке таблиц: {e}")
        return False

    logger.info("✅ Проверка миграций пройдена успешно")
    return True


if __name__ == "__main__":
    success = asyncio.run(check_migrations())
    sys.exit(0 if success else 1)
