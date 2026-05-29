from typing import List, Optional
from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory
from bot.models import Item, Category


class ItemRepository:
    """Репозиторий для работы с товарами."""

    @staticmethod
    async def get_all_items() -> List[Item]:
        async with get_async_session_factory()() as session:
            stmt = select(Item).order_by(Item.text)
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_items_by_category(category_id: int) -> List[Item]:
        async with get_async_session_factory()() as session:
            stmt = select(Item).where(Item.category_id == category_id).order_by(Item.text)
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def delete_item(item_id: int) -> bool:
        async with get_async_session_factory()() as session:
            item = await session.get(Item, item_id)
            if not item:
                return False
            await session.delete(item)
            await session.commit()
            return True

    @staticmethod
    async def count_all_items() -> int:
        async with get_async_session_factory()() as session:
            return await session.scalar(select(func.count()).select_from(Item)) or 0

    @staticmethod
    async def count_booked_items() -> int:
        async with get_async_session_factory()() as session:
            return await session.scalar(
                select(func.count()).select_from(Item).where(Item.is_booked == True)
            ) or 0

    @staticmethod
    async def clear_all_items() -> int:
        """Полная очистка ассортимента."""
        async with get_async_session_factory()() as session:
            result = await session.execute(delete(Item))
            await session.commit()
            return result.rowcount
