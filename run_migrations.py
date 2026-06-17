#!/usr/bin/env python3
from alembic.config import Config
from alembic import command
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main():
    logger.info("🔄 Применяем миграции Alembic...")

    # Пытаемся выполнить проверку (но не падаем, если что-то пошло не так)
    try:
        from scripts.check_migrations import check_migrations
        if not check_migrations():
            logger.warning("⚠️ Проверка миграций не прошла, но продолжаем применение")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось выполнить проверку миграций: {e}")

    # Применяем миграции
    try:
        alembic_cfg = Config("alembic.ini")
        command.upgrade(alembic_cfg, "head")
        logger.info("✅ Все миграции успешно применены!")
        command.current(alembic_cfg)
    except Exception as e:
        logger.error(f"❌ Ошибка при применении миграций: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
