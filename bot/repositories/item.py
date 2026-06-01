import logging
from typing import Optional
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.models import Category, Item

logger = logging.getLogger(__name__)


class ItemRepository:

    @staticmethod
    async def get_or_create_category(name: str, conn: Optional[AsyncSession] = None) -> int:
        session = conn
        own = False
        if session is None:
            from bot.db import get_async_session_factory
            session = get_async_session_factory()()
            own = True

        try:
            result = await session.execute(
                select(Category).where(func.lower(Category.name) == func.lower(name.strip()))
            )
            cat = result.scalar_one_or_none()
            if cat:
                return cat.id

            max_order = (await session.execute(select(func.coalesce(func.max(Category.sort_order), 0)))).scalar() or 0
            new_cat = Category(name=name.strip(), sort_order=max_order + 1)
            session.add(new_cat)
            await session.flush()
            return new_cat.id
        finally:
            if own:
                await session.close()

    @staticmethod
    async def add_item(text: str, serial: Optional[str], category_id: int,
                       is_booked: bool = False, conn: Optional[AsyncSession] = None):
        session = conn
        own = False
        if session is None:
            from bot.db import get_async_session_factory
            session = get_async_session_factory()()
            own = True

        try:
            item = Item(
                text=text.strip(),
                serial=serial.strip().upper() if serial else None,
                category_id=category_id,
                is_booked=is_booked
            )
            session.add(item)
            await session.flush()
        finally:
            if own:
                await session.commit()
                await session.close()
