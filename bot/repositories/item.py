import logging
from typing import Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Category, Item
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class ItemRepository:

    @staticmethod
    async def get_or_create_category(name: str, conn: Optional[AsyncSession] = None) -> int:
        """Возвращает ID категории. Если нет — создаёт (новые категории внизу)."""
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

            # Создаём новую категорию в конце
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
        """Добавляет товар."""
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
    async def bulk_replace_assortment(categories: list, conn: Optional[AsyncSession] = None):
        """
        Полная замена ассортимента.
        categories — список словарей: [{"header": "iPhone:", "items": ["текст (серийник)", ...]}, ...]
        """
        session = conn
        own_session = False

        if session is None:
            from bot.db import get_async_session_factory
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True

        try:
            if own_session:
                await session.begin()

            # Удаляем все товары (кроме системных)
            await session.execute(
                text("""
                    DELETE FROM items 
                    WHERE category_id NOT IN (
                        SELECT id FROM categories WHERE name = '__SYSTEM__'
                    )
                """)
            )

            # Удаляем все категории, кроме системной
            await session.execute(
                text("DELETE FROM categories WHERE name != '__SYSTEM__'")
            )

            # Создаём новые категории и товары
            for cat_data in categories:
                header = cat_data.get("header", "").strip()
                if not header:
                    continue

                cat_id = await ItemRepository.get_or_create_category(header, conn=session)

                for item_text in cat_data.get("items", []):
                    if not item_text.strip():
                        continue

                    serials = extract_serials(item_text)
                    serial = serials[0] if serials else None
                    is_booked = "Бронь от" in item_text or "БРОНЬ" in item_text.upper()

                    await ItemRepository.add_item(
                        text=item_text.strip(),
                        serial=serial,
                        category_id=cat_id,
                        is_booked=is_booked,
                        conn=session
                    )

            if own_session:
                await session.commit()

            logger.info(f"Ассортимент успешно заменён. Категорий: {len(categories)}")

        except Exception as e:
            if own_session:
                await session.rollback()
            logger.exception("Ошибка при bulk_replace_assortment")
            raise e
        finally:
            if own_session:
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
