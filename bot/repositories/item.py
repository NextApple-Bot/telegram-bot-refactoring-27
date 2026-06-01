import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.models import Category, Item
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class ItemRepository:

    @staticmethod
    async def get_or_create_category(name: str, conn: Optional[AsyncSession] = None) -> int:
        """Создаёт категорию, если её нет. Новые категории добавляются в конец."""
        session = conn
        own_session = False

        if session is None:
            from bot.db import get_async_session_factory
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True

        try:
            result = await session.execute(
                select(Category).where(func.lower(Category.name) == func.lower(name.strip()))
            )
            category = result.scalar_one_or_none()

            if category:
                return category.id

            # Новая категория в конец
            max_order_result = await session.execute(
                select(func.coalesce(func.max(Category.sort_order), 0))
            )
            max_order = max_order_result.scalar() or 0

            new_category = Category(name=name.strip(), sort_order=max_order + 1)
            session.add(new_category)
            await session.flush()
            return new_category.id

        finally:
            if own_session:
                await session.close()

    @staticmethod
    async def add_item(
        text: str,
        serial: Optional[str],
        category_id: int,
        is_booked: bool = False,
        conn: Optional[AsyncSession] = None
    ):
        """Добавляет товар в БД."""
        session = conn
        own_session = False

        if session is None:
            from bot.db import get_async_session_factory
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True

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
            if own_session:
                await session.commit()
                await session.close()

    @staticmethod
    async def get_all_categories_with_items(conn: Optional[AsyncSession] = None) -> List[Dict[str, Any]]:
        """Возвращает все категории с товарами (для AssortmentService и arrival)."""
        session = conn
        own_session = False

        if session is None:
            from bot.db import get_async_session_factory
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True

        try:
            result = await session.execute(
                select(Category)
                .options(selectinload(Category.items))
                .order_by(Category.sort_order)
            )
            categories = result.scalars().all()

            data = []
           
