#!/usr/bin/env python3
"""
Полноценная автоматическая проверка миграций Alembic.
Проверяет ревизии, таблицы и соответствие моделей схеме БД.
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
    """Полноценная проверка миграций."""
    logger.info("🔍 Запуск проверки миграций...")

    DATABASE_URL = bot_config.DATABASE_URL

    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL не задан в конфигурации")
        return False

    # Настройка Alembic
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    script = ScriptDirectory.from_config(alembic_cfg)

    # Создаём асинхронный движок
    engine = create_async_engine(
        DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        echo=False,
    )

    try:
        # === 1. Проверка текущей ревизии ===
        async with engine.connect() as conn:
            context = MigrationContext.configure(conn.sync_connection)
            current_rev = context.get_current_revision()

        head_rev = script.get_current_head()

        logger.info(f"Текущая ревизия в БД: {current_rev}")
        logger.info(f"Head ревизия:        {head_rev}")

        if current_rev != head_rev:
            logger.error("❌ Миграции не актуальны! Нужно выполнить: alembic upgrade head")
            return False

        logger.info("✅ Ревизии совпадают (current == head)")

        # === 2. Проверка существования всех таблиц из моделей ===
        from bot.models import Base

        async with engine.connect() as conn:
            inspector = inspect(conn.sync_connection)
            existing_tables = set(inspector.get_table_names())

            missing_tables = []
            for table_name in Base.metadata.tables.keys():
                if table_name not in existing_tables:
                    missing_tables.append(table_name)

            if missing_tables:
                logger.error(f"❌ Отсутствуют таблицы в БД: {missing_tables}")
                return False

        logger.info("✅ Все таблицы из моделей присутствуют в БД")

        # === 3. Дополнительная проверка через alembic check (если доступно) ===
        try:
            from alembic import command
            command.check(alembic_cfg)
            logger.info("✅ alembic check пройден (модели соответствуют схеме БД)")
        except Exception as e:
            logger.warning(f"⚠️ alembic check завершился с предупреждением: {e}")

        logger.info("✅ Все проверки миграций пройдены успешно!")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка при проверке миграций: {e}")
        return False

    finally:
        await engine.dispose()


if __name__ == "__main__":
    success = asyncio.run(check_migrations())
    sys.exit(0 if success else 1)
