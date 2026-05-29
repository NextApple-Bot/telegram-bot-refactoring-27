# bot/db.py
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bot import config

logger = logging.getLogger(__name__)

_async_engine = None
_async_session_factory = None


def get_async_session_factory():
    global _async_engine, _async_session_factory
    if _async_session_factory is None:
        db_url = config.DATABASE_URL
        if db_url.startswith("postgresql://"):
            db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
        
        min_size = getattr(config, 'DB_POOL_MIN_SIZE', 1)
        max_size = getattr(config, 'DB_POOL_MAX_SIZE', 5)
        
        _async_engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=min_size,
            max_overflow=max_size - min_size,
            pool_recycle=300,
            connect_args={"ssl": False}
        )
        _async_session_factory = async_sessionmaker(
            bind=_async_engine,
            expire_on_commit=False
        )
        logger.info("✅ Фабрика асинхронных сессий SQLAlchemy создана")
    return _async_session_factory


# Алиас для обратной совместимости (исправляет ошибку ImportError)
get_pool = get_async_session_factory


async def dispose_engine():
    global _async_engine, _async_session_factory
    if _async_engine:
        await _async_engine.dispose()
        _async_engine = None
        _async_session_factory = None
        logger.info("✅ Движок SQLAlchemy остановлен")


async def check_db_health() -> bool:
    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
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
