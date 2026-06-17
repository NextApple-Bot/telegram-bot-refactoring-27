#!/usr/bin/env python3
"""
Полноценная проверка миграций (синхронная версия — стабильная).
"""

import logging
import sys

from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from bot.config import config as bot_config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def check_migrations() -> bool:
    """Проверка миграций (синхронно — надёжно для pre-deploy)."""
    logger.info("🔍 Запуск проверки миграций...")

    DATABASE_URL = bot_config.DATABASE_URL

    if not DATABASE_URL:
        logger.error("❌ DATABASE_URL не задан")
        return False

    # Настройка Alembic
    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)

    script = ScriptDirectory.from_config(alembic_cfg)

    # Создаём синхронный движок (более стабильный для pre-deploy)
    engine = create_engine(DATABASE_URL)

    try:
        # 1. Проверка ревизий
        with engine.connect() as conn:
            context = MigrationContext.configure(conn)
            current_rev = context.get_current_revision()

        head_rev = script.get_current_head()

        logger.info(f"Текущая ревизия в БД: {current_rev}")
        logger.info(f"Head ревизия:        {head_rev}")

        if current_rev != head_rev:
            logger.error("❌ Миграции не актуальны!")
            return False

        logger.info("✅ Ревизии совпадают")

        # 2. Проверка таблиц
        from bot.models import Base

        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        for table in Base.metadata.tables.keys():
            if table not in existing_tables:
                logger.error(f"❌ Таблица '{table}' отсутствует в БД")
                return False

        logger.info("✅ Все таблицы из моделей присутствуют в БД")

        # 3. alembic check (опционально)
        try:
            from alembic import command
            command.check(alembic_cfg)
            logger.info("✅ alembic check пройден")
        except Exception as e:
            logger.warning(f"⚠️ alembic check: {e}")

        logger.info("✅ Проверка миграций пройдена успешно")
        return True

    except Exception as e:
        logger.error(f"❌ Ошибка при проверке миграций: {e}")
        return False

    finally:
        engine.dispose()


if __name__ == "__main__":
    success = check_migrations()
    sys.exit(0 if success else 1)
