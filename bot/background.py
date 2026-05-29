import asyncio
import logging
from datetime import datetime, timedelta

from bot.config import config
from bot.db import get_async_session_factory

logger = logging.getLogger(__name__)


async def cleanup_old_records():
    """Очистка старых записей (раз в сутки)."""
    try:
        async with get_async_session_factory()() as session:
            async with session.begin():
                # Удаляем обработанные сообщения старше 30 дней
                await session.execute("""
                    DELETE FROM processed_messages 
                    WHERE processed_at < NOW() - INTERVAL '30 days'
                """)
                # Удаляем старые ежедневные платежи
                await session.execute("""
                    DELETE FROM daily_payments 
                    WHERE created_at < NOW() - INTERVAL '180 days'
                """)
                logger.info("✅ Выполнена очистка старых записей")
    except Exception as e:
        logger.exception(f"Ошибка очистки старых записей: {e}")


async def cleanup_sold_items():
    """Очистка проданных товаров старше 7 дней."""
    try:
        cutoff = datetime.now() - timedelta(days=7)
        async with get_async_session_factory()() as session:
            async with session.begin():
                result = await session.execute("""
                    DELETE FROM deleted_items 
                    WHERE reason = 'sale_from_admin' 
                    AND deleted_at < :cutoff
                """, {"cutoff": cutoff})
                logger.info(f"✅ Очищено {result.rowcount} проданных товаров")
    except Exception as e:
        logger.exception(f"Ошибка очистки проданных товаров: {e}")


async def start_background_tasks(bot, dp):
    """Запуск всех фоновых задач."""
    logger.info("🚀 Запуск фоновых задач...")

    # Задача 1: Ежедневная очистка
    async def daily_cleanup():
        while True:
            await asyncio.sleep(86400)  # 24 часа
            await cleanup_old_records()
            await cleanup_sold_items()

    # Запускаем в фоне
    asyncio.create_task(daily_cleanup())

    logger.info("✅ Фоновые задачи успешно запущены")
