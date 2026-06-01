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
        # ... (код из предыдущего сообщения, оставляю коротко)
        ...

    @staticmethod
    async def add_item(text: str, serial: Optional[str], category_id: int,
                       is_booked: bool = False, conn: Optional[AsyncSession] = None):
        # ... (код)
        ...

    @staticmethod
    async def get_all_categories_with_items(conn: Optional[AsyncSession] = None) -> List[Dict[str, Any]]:
        """Возвращает категории с товарами (используется в AssortmentService.load_inventory)."""
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
            for cat in categories:
                if cat.name == "__SYSTEM__":
                    continue
                items = [{"text": item.text, "serial": item.serial} for item in getattr(cat, 'items', [])]
                data.append({"header": cat.name, "items": items})
            return data
        finally:
            if own_session:
                await session.close()

    @staticmethod
    async def bulk_replace_assortment(categories: list, conn: Optional[AsyncSession] = None):
        # ... (полный код из предыдущего сообщения)
        ...

    @staticmethod
    async def get_item_id_by_serial(serial: str, conn: Optional[AsyncSession] = None) -> Optional[int]:
        # ... (код)
        ...
