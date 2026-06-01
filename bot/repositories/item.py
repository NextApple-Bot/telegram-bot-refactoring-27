import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Category, Item

logger = logging.getLogger(__name__)


class ItemRepository:

    @staticmethod
    async def get_or_create_category(name: str, conn: Optional[AsyncSession] = None) -> int:
        """
        Возвращает ID категории. Если категории нет — создаёт её.
        Новые категории добавляются в конец списка (максимальный sort_order + 1).
        """
        session = conn
        own_session = False

        if session is None:
            from bot.db import get_async_session_factory
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True

        try:
            # Ищем категорию (без учёта регистра)
            result = await session.execute(
                select(Category).where(func.lower(Category.name) == func.lower(name.strip()))
            )
            category = result.scalar_one_or_none()

            if category:
                return category.id

            # Создаём новую категорию в конце списка
            max_order_result = await session.execute(
                select(func.coalesce(func.max(Category.sort_order), 0))
            )
            max_order = max_order_result.scalar() or 0

            new_category = Category(
                name=name.strip(),
                sort_order=max_order + 1
            )
            session.add(new_category)
            await session.flush()  # получаем id

            logger.info(f"Создана новая категория: {name} (sort_order={new_category.sort_order})")
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
    ) -> int:
        """
        Добавляет новый товар в ассортимент.
        """
        session = conn
        own_session = False

        if session is None:
            from bot.db import get_async_session_factory
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True

        try:
            new_item = Item(
                text=text.strip(),
                serial=serial.strip().upper() if serial else None,
                category_id=category_id,
                is_booked=is_booked
            )
            session.add(new_item)
            await session.flush()
            return new_item.id

        finally:
            if own_session:
                await session.commit()
                await session.close()

    @staticmethod
    async def get_item_id_by_serial(serial: str, conn: Optional[AsyncSession] = None) -> Optional[int]:
        """Возвращает ID товара по серийному номеру."""
        session = conn
        own_session = False

        if session is None:
            from bot.db import get_async_session_factory
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True

        try:
            result = await session.execute(
                select(Item.id).where(Item.serial == serial.strip().upper())
            )
            return result.scalar_one_or_none()
        finally:
            if own_session:
                await session.close()
