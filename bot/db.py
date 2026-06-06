import asyncio
import logging
import os
from functools import lru_cache, wraps
from typing import Optional

import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from bot import config

logger = logging.getLogger(__name__)


def retry_on_db_error(retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Декоратор для повторных попыток при ошибках подключения к БД."""
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
                        logger.warning(
                            f"Ошибка подключения к БД (попытка {attempt + 1}/{retries}): {e}. "
                            f"Повтор через {wait:.1f}с"
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Все попытки подключения исчерпаны: {e}")
                        raise
                except Exception:
                    raise
            raise last_exception
        return wrapper
    return decorator


# ============================================================
# Asyncpg пул (для старых репозиториев)
# ============================================================

_pool: Optional[asyncpg.Pool] = None


@retry_on_db_error(retries=5, delay=2.0)
async def get_pool() -> asyncpg.Pool:
    """Возвращает пул соединений asyncpg."""
    global _pool
    if _pool is None:
        min_size = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
        max_size = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

        dsn = config.DATABASE_URL
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)

        _pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=60,
            max_inactive_connection_lifetime=300,
        )
        logger.info(f"✅ Asyncpg пул создан (min={min_size}, max={max_size})")
    return _pool


async def close_pool():
    """Закрывает пул asyncpg."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ Asyncpg пул закрыт")


# ============================================================
# SQLAlchemy 2.0 async (основной способ)
# ============================================================

_engine = None
_async_session_factory = None


def get_async_engine():
    """Создаёт SQLAlchemy async engine."""
    global _engine
    if _engine is None:
        database_url = config.DATABASE_URL
        if database_url.startswith("postgresql://"):
            database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)

        _engine = create_async_engine(
            database_url,
            pool_pre_ping=True,
            echo=False,
            poolclass=NullPool,
        )
        logger.info("✅ SQLAlchemy async engine создан")
    return _engine


@lru_cache
def get_async_session_factory() -> async_sessionmaker:
    """Фабрика асинхронных сессий SQLAlchemy 2.0."""
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
    """Закрывает SQLAlchemy engine."""
    global _engine, _async_session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
        logger.info("✅ SQLAlchemy engine закрыт")


# ============================================================
# Инициализация и healthcheck
# ============================================================

async def init_db():
    """
    Инициализация подключения к БД.
    В текущей архитектуре миграции выполняются через Alembic,
    поэтому здесь только проверка подключения.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("SELECT 1")
        logger.info("✅ Подключение к PostgreSQL успешно установлено")
    except Exception as e:
        logger.error(f"❌ Ошибка инициализации БД: {e}")
        raise


async def check_db_health() -> bool:
    """
    Проверка здоровья подключения к БД через SQLAlchemy.
    Это более единообразно с основной частью приложения (v27).
    """
    try:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB healthcheck failed: {e}")
        return False


async def check_redis_health() -> bool:
    """Проверка здоровья Redis (если настроен)."""
    if not config.REDIS_URL:
        return True
    try:
        import redis.asyncio as redis
        r = redis.from_url(config.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        return True
    except Exception as e:
        logger.error(f"Redis healthcheck failed: {e}")
        return False
