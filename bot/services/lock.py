import logging
from contextlib import asynccontextmanager

from bot.services.cache import cache

logger = logging.getLogger(__name__)


@asynccontextmanager
async def redis_lock(key: str, ttl: int = 30):
    """Асинхронный контекстный менеджер для Redis-блокировки."""
    acquired = await cache.lock(key, ttl=ttl)
    if not acquired:
        logger.warning(f"Не удалось получить блокировку {key}")
        yield False
        return
    try:
        yield True
    finally:
        await cache.unlock(key)
