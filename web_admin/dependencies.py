from typing import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency для получения асинхронной сессии БД.
    
    Полная реализация из канонической версии 26 (золотой эталон).
    Используется в web_admin/routes/assortment/manage.py и других роутах админ-панели.
    """
    async_session_factory = get_async_session_factory()
    async with async_session_factory() as session:
        yield session


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Алиас для обратной совместимости."""
    async for session in get_async_session():
        yield session
