import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from bot.db import get_async_session_factory
from bot.models import Category, Item
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class ItemRepository:

    @staticmethod
    async def get_or_create_category(name: str, conn=None) -> int:
        """Возвращает ID категории, создаёт при отсутствии."""
        norm_name = name.strip().lower().rstrip(':')
        async def _impl(session):
            result = await session.execute(
                select(Category.id).where(func.lower(Category.name) == norm_name)
            )
            cat_id = result.scalar_one_or_none()
            if cat_id:
                return cat_id

            max_order = await session.execute(
                select(func.coalesce(func.max(Category.sort_order), 0))
            )
            new_order = (max_order.scalar() or 0) + 1

            new_cat = Category(name=name.strip(), sort_order=new_order)
            session.add(new_cat)
            try:
                await session.flush()
                return new_cat.id
            except IntegrityError:
                await session.rollback()
                result = await session.execute(
                    select(Category.id).where(func.lower(Category.name) == norm_name)
                )
                return result.scalar_one()

        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                return await _impl(session)

    @staticmethod
    async def add_item(
        text: str,
        serial: Optional[str] = None,
        category_id: Optional[int] = None,
        is_booked: bool = False,
        conn=None
    ):
        """Добавляет товар."""
        async def _impl(session):
            item = Item(
                text=text.strip(),
                serial=serial.strip().upper() if serial else None,
                category_id=category_id,
                is_booked=is_booked
            )
            session.add(item)
            await session.flush()

        if conn is not None:
            await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                await _impl(session)

    @staticmethod
    async def get_all_categories_with_items(conn=None) -> List[Dict[str, Any]]:
        """Возвращает все категории с товарами (для кэша и отображения)."""
        async def _impl(session):
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
                items = [{"text": item.text, "serial": item.serial} for item in cat.items]
                data.append({"header": cat.name, "items": items})
            return data

        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session:
                return await _impl(session)

    @staticmethod
    async def bulk_replace_assortment(categories: list, conn=None):
        """Полная замена ассортимента."""
        async def _impl(session):
            # Удаляем все товары кроме системных
            await session.execute(
                "DELETE FROM items WHERE category_id NOT IN "
                "(SELECT id FROM categories WHERE name = '__SYSTEM__')"
            )
            await session.execute("DELETE FROM categories WHERE name != '__SYSTEM__'")

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
                    is_booked = "Бронь" in item_text.upper()

                    await ItemRepository.add_item(
                        text=item_text.strip(),
                        serial=serial,
                        category_id=cat_id,
                        is_booked=is_booked,
                        conn=session
                    )

        if conn is not None:
            await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                await _impl(session)

    @staticmethod
    async def get_item_id_by_serial(serial: str, conn=None) -> Optional[int]:
        if not serial:
            return None
        normalized = serial.strip().upper()
        async def _impl(session):
            result = await session.execute(
                select(Item.id).where(func.upper(Item.serial) == normalized)
            )
            return result.scalar_one_or_none()

        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session:
                return await _impl(session)
