import asyncio
import logging
import os
from functools import lru_cache, wraps

import asyncpg
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot import config

logger = logging.getLogger(__name__)


def retry_on_db_error(retries=3, delay=1, backoff=2):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except (asyncpg.exceptions.ConnectionFailureError,
                        asyncpg.exceptions.InterfaceError,
                        asyncpg.exceptions.PostgresConnectionError) as e:
                    last_exception = e
                    if attempt < retries - 1:
                        wait = delay * (backoff ** attempt)
                        logger.warning(f"Ошибка БД (попытка {attempt+1}/{retries}): {e}. Повтор через {wait}с")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Все попытки исчерпаны: {e}")
                        raise
                except Exception:
                    raise
            raise last_exception
        return wrapper
    return decorator


_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        min_size = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
        max_size = int(os.getenv("DB_POOL_MAX_SIZE", "5"))
        last_exception = None
        for attempt in range(5):
            try:
                _pool = await asyncpg.create_pool(
                    config.DATABASE_URL,
                    min_size=min_size,
                    max_size=max_size,
                    command_timeout=60,
                    max_inactive_connection_lifetime=300
                )
                logger.info(f"✅ Пул соединений создан (min={min_size}, max={max_size})")
                break
            except Exception as e:
                last_exception = e
                wait = 2 ** attempt
                logger.warning(f"Не удалось создать пул (попытка {attempt+1}/5): {e}. Повтор через {wait}с")
                await asyncio.sleep(wait)
        else:
            logger.error("Все попытки создания пула провалились")
            raise last_exception
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ Пул соединений закрыт")


# ============================================================
# SQLAlchemy async session factory (для main.py и совместимости)
# ============================================================

_engine = None
_async_session_factory = None


def get_async_engine():
    """Возвращает SQLAlchemy async engine."""
    global _engine
    if _engine is None:
        database_url = config.DATABASE_URL
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        _engine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            echo=False,
        )
        logger.info("✅ SQLAlchemy async engine создан")
    return _engine


@lru_cache
def get_async_session_factory() -> async_sessionmaker:
    """Возвращает фабрику async сессий SQLAlchemy (нужна для main.py)."""
    global _async_session_factory
    if _async_session_factory is None:
        engine = get_async_engine()
        _async_session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
        )
        logger.info("✅ SQLAlchemy async_sessionmaker создан")
    return _async_session_factory


async def dispose_engine():
    """Закрывает SQLAlchemy engine при shutdown."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("✅ SQLAlchemy engine закрыт")


# ============================================================
# Инициализация БД (asyncpg)
# ============================================================

async def init_db():
    """Создаёт таблицы, индексы и недостающие колонки."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # ... (весь твой текущий код init_db остаётся без изменений)
        # Я оставил его для brevity, но в реальном файле он должен быть полностью
        pass  # ← замени на полный код init_db из твоего файла

    logger.info("✅ Инициализация БД завершена")


async def check_db_health() -> bool:
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('SELECT 1')
        return True
    except Exception:
        return False


async def check_redis_health() -> bool:
    if not config.REDIS_URL:
        return True
    try:
        import redis.asyncio as redis
        r = redis.from_url(config.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False
