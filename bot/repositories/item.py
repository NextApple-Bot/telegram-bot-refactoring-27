from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, select, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory
from bot.models import Category, DeletedItem, Item
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class ItemRepository:
    """Репозиторий для работы с товарами (полная версия из старого рабочего бота)."""

    @staticmethod
    async def get_or_create_category(name: str, conn: AsyncSession | None = None) -> int:
        """Получить ID категории по имени или создать новую."""
        norm_name = name.lower().rstrip(':')

        async def _impl(session: AsyncSession):
            result = await session.execute(
                select(Category.id).where(func.lower(Category.name) == norm_name)
            )
            cat_id = result.scalar_one_or_none()
            if cat_id:
                return cat_id

            max_order = await session.execute(
                select(func.coalesce(func.max(Category.sort_order), -1))
            )
            new_order = max_order.scalar() + 1

            new_cat = Category(name=name, sort_order=new_order)
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
    async def bulk_replace_assortment(categories: list[dict], conn: AsyncSession | None = None) -> None:
        """Полная замена ассортимента."""
        from bot.services.cache import cache

        own_session = False
        if conn is None:
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True
        else:
            session = conn

        try:
            if own_session:
                await session.begin()

            # Удаляем все товары кроме системных
            sys_cat = await session.execute(
                select(Category.id).where(Category.name == '__SYSTEM__')
            )
            sys_id = sys_cat.scalar_one_or_none()

            if sys_id:
                await session.execute(
                    delete(Item).where(Item.category_id != sys_id)
                )
            else:
                await session.execute(delete(Item))

            # Удаляем категории кроме системной
            await session.execute(
                delete(Category).where(Category.name != '__SYSTEM__')
            )
            await session.flush()

            # Вставляем новые категории и товары
            for idx, cat_data in enumerate(categories):
                cat_name = cat_data.get('header') or cat_data.get('name', 'Без категории')
                cat_id = await ItemRepository.get_or_create_category(cat_name, conn=session)

                for item_text in cat_data.get('items', []):
                    if not item_text or not item_text.strip():
                        continue

                    serials = extract_serials(item_text)
                    serial = serials[0].strip().upper() if serials else None
                    is_booked = 'Бронь от' in item_text

                    new_item = Item(
                        text=item_text,
                        serial=serial,
                        category_id=cat_id,
                        is_booked=is_booked
                    )
                    session.add(new_item)

            if own_session:
                await session.commit()

            await cache.delete("assortment:all")
            logger.info(f"✅ Ассортимент полностью заменён ({len(categories)} категорий)")

        except Exception as e:
            if own_session:
                await session.rollback()
            logger.exception("Ошибка при bulk_replace_assortment")
            raise
        finally:
            if own_session:
                await session.close()

    @staticmethod
    async def get_all_categories_with_items(conn: AsyncSession | None = None) -> list[dict]:
        """Получить все категории с товарами."""
        async def _impl(session: AsyncSession):
            result = await session.execute(
                select(Category.name, Item.text)
                .outerjoin(Item, Category.id == Item.category_id)
                .where(Category.name != '__SYSTEM__')
                .order_by(Category.sort_order, Category.name, Item.id)
            )
            rows = result.all()

            categories_dict: dict[str, list[str]] = {}
            for row in rows:
                cat_name = row.name
                if cat_name not in categories_dict:
                    categories_dict[cat_name] = []
                if row.text:
                    categories_dict[cat_name].append(row.text)

            return [{"header": cat, "items": items} for cat, items in categories_dict.items()]

        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session:
                return await _impl(session)

    @staticmethod
    async def get_item_id_by_serial(serial: str, conn: AsyncSession | None = None) -> int | None:
        if not serial:
            return None
        normalized = serial.strip().upper()

        async def _impl(session: AsyncSession):
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

    @staticmethod
    async def get_item_by_serial(serial: str, conn: AsyncSession | None = None) -> dict | None:
        if not serial:
            return None
        normalized = serial.strip().upper()

        async def _impl(session: AsyncSession):
            result = await session.execute(
                select(Item.id, Item.text, Item.category_id, Category.name.label("category_name"))
                .join(Category, Item.category_id == Category.id)
                .where(func.upper(Item.serial) == normalized)
            )
            row = result.mappings().one_or_none()
            return dict(row) if row else None

        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session:
                return await _impl(session)

    @staticmethod
    async def remove_item_by_serial(serial: str, conn: AsyncSession | None = None) -> int:
        if not serial:
            return 0
        normalized = serial.strip().upper()

        async def _impl(session: AsyncSession):
            result = await session.execute(
                select(Item.id).where(func.upper(Item.serial) == normalized)
            )
            item_id = result.scalar_one_or_none()
            if item_id:
                item = await session.get(Item, item_id)
                if item:
                    await session.delete(item)
                    await session.flush()
                    return 1
            return 0

        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                return await _impl(session)
