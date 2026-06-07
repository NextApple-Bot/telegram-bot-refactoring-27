import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import Bot, Dispatcher          # ← добавлен импорт

from bot import config
from bot.db import get_async_session_factory
from bot.services.cache import cache

logger = logging.getLogger(__name__)


# ============================================================
# Константы для блокировок (защита от дублирования при масштабировании)
# ============================================================

CLEANUP_LOCK_KEY = "background:cleanup_old_records:lock"
CLEANUP_SOLD_LOCK_KEY = "background:cleanup_sold_items:lock"
WEBHOOK_HEALTHCHECK_LOCK_KEY = "background:webhook_healthcheck:lock"

LOCK_TTL = 86400 * 2  # 2 дня


# ============================================================
# Вспомогательные функции
# ============================================================

async def run_with_lock(lock_key: str, task_func, ttl: int = LOCK_TTL) -> None:
    """
    Выполняет задачу под распределённой блокировкой Redis.
    Если Redis не настроен — выполняет задачу без блокировки.
    """
    if not config.REDIS_URL:
        await task_func()
        return

    acquired = await cache.lock(lock_key, ttl=ttl)
    if acquired:
        try:
            await task_func()
        finally:
            await cache.unlock(lock_key)
    else:
        logger.debug(f"Блокировка {lock_key} уже захвачена другим инстансом")


# ============================================================
# Фоновые задачи очистки
# ============================================================

async def cleanup_old_records() -> None:
    """Очистка старых записей (processed_messages и daily_payments)."""
    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            # Удаляем обработанные сообщения старше 30 дней
            result1 = await session.execute(
                "DELETE FROM processed_messages WHERE processed_at < NOW() - INTERVAL '30 days'"
            )
            # Удаляем старые ежедневные платежи (храним 180 дней)
            result2 = await session.execute(
                "DELETE FROM daily_payments WHERE created_at < NOW() - INTERVAL '180 days'"
            )

            logger.info(
                f"🧹 Очистка завершена: processed_messages={result1.rowcount}, "
                f"daily_payments={result2.rowcount}"
            )
    except Exception as e:
        logger.exception(f"Ошибка при очистке старых записей: {e}")


async def cleanup_sold_items() -> None:
    """Очистка записей о проданных товарах старше 7 дней."""
    try:
        cutoff = datetime.now() - timedelta(days=7)
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            result = await session.execute(
                """
                DELETE FROM deleted_items 
                WHERE reason = 'sale_from_admin' 
                  AND deleted_at < :cutoff
                """,
                {"cutoff": cutoff},
            )
            logger.info(f"🧹 Очищено {result.rowcount} старых записей о продажах из админки")
    except Exception as e:
        logger.exception(f"Ошибка при очистке проданных товаров: {e}")


# ============================================================
# Healthcheck вебхука
# ============================================================

async def webhook_healthcheck(bot: Bot, dp: Dispatcher) -> None:
    """Периодическая проверка и восстановление вебхука при необходимости."""
    from bot.webhook_utils import check_and_set_webhook

    try:
        # Передаём bot и dp в функцию проверки вебхука
        await check_and_set_webhook(bot, dp)
    except Exception as e:
        logger.exception(f"Ошибка при healthcheck вебхука: {e}")


# ============================================================
# Основные циклы фоновых задач
# ============================================================

async def _run_periodic_task(
    task_name: str,
    task_func,
    interval_seconds: int,
    lock_key: Optional[str] = None,
    *args,
    **kwargs,
) -> None:
    """Универсальный цикл для периодического выполнения задачи."""
    logger.info(f"▶️ Запущена фоновая задача: {task_name} (интервал: {interval_seconds}s)")

    while True:
        try:
            if lock_key:
                await run_with_lock(lock_key, lambda: task_func(*args, **kwargs))
            else:
                await task_func(*args, **kwargs)
        except Exception as e:
            logger.exception(f"Ошибка в фоновой задаче {task_name}: {e}")

        await asyncio.sleep(interval_seconds)


async def start_background_tasks(bot: Optional[Bot] = None, dp: Optional[Dispatcher] = None) -> None:
    """
    Запуск всех фоновых задач приложения.
    """
    logger.info("🚀 Запуск фоновых задач...")

    # Задача 1: Ежедневная очистка старых записей
    asyncio.create_task(
        _run_periodic_task(
            task_name="cleanup_old_records",
            task_func=cleanup_old_records,
            interval_seconds=86400,  # раз в сутки
            lock_key=CLEANUP_LOCK_KEY,
        )
    )

    # Задача 2: Очистка проданных товаров
    asyncio.create_task(
        _run_periodic_task(
            task_name="cleanup_sold_items",
            task_func=cleanup_sold_items,
            interval_seconds=86400,
            lock_key=CLEANUP_SOLD_LOCK_KEY,
        )
    )

    # Задача 3: Healthcheck вебхука (каждые 5 минут)
    if bot and dp:
        asyncio.create_task(
            _run_periodic_task(
                task_name="webhook_healthcheck",
                task_func=webhook_healthcheck,
                interval_seconds=300,  # раз в 5 минут
                lock_key=WEBHOOK_HEALTHCHECK_LOCK_KEY,
                bot=bot,
                dp=dp,
            )
        )
    else:
        logger.warning("⚠️ Healthcheck вебхука не запущен: не переданы bot и dp")

    logger.info("✅ Все фоновые задачи успешно запущены")
