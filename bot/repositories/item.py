from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import func, select, update, delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Category, DeletedItem, Item

logger = logging.getLogger(__name__)


class ItemRepository:
    """Репозиторий для работы с товарами и категориями."""

    @staticmethod
    async def get_or_create_category(name: str, conn: AsyncSession) -> Category:
        """Получить категорию по имени или создать новую."""
        name = name.strip()
        if not name:
            raise ValueError("Название категории не может быть пустым")

        result = await conn.execute(
            select(Category).where(func.lower(Category.name) == func.lower(name))
        )
        category = result.scalar_one_or_none()

        if category:
            return category

        # Создаём новую категорию
        max_order_result = await conn.execute(select(func.coalesce(func.max(Category.sort_order), -1)))
        new_sort_order = max_order_result.scalar() + 1

        new_category = Category(name=name, sort_order=new_sort_order)
        conn.add(new_category)
        await conn.flush()
        return new_category

    @staticmethod
    async def bulk_replace_assortment(categories: list[dict], conn: AsyncSession | None = None) -> None:
        """
        Полная замена ассортимента.
        categories = [
            {"name": "iPhone", "items": [{"text": "...", "serial": "..."}, ...]},
            ...
        ]
        """
        own_session = False
        if conn is None:
            from bot.db import get_async_session_factory
            session = get_async_session_factory()()
            own_session = True
        else:
            session = conn

        try:
            if own_session:
                await session.begin()

            # Удаляем все товары (кроме системных)
            await session.execute(delete(Item).where(Item.id != 0))

            for cat_data in categories:
                cat_name = cat_data.get("name", "").strip()
                if not cat_name:
                    continue

                category = await ItemRepository.get_or_create_category(cat_name, session)

                for item_data in cat_data.get("items", []):
                    text = item_data.get("text", "").strip()
                    if not text:
                        continue

                    new_item = Item(
                        text=text,
                        serial=item_data.get("serial"),
                        category_id=category.id,
                        is_booked=False
                    )
                    session.add(new_item)

            if own_session:
                await session.commit()
                logger.info(f"Ассортимент полностью заменён ({len(categories)} категорий)")

        except Exception as e:
            if own_session:
                await session.rollback()
            logger.exception("Ошибка при массовой замене ассортимента")
            raise
        finally:
            if own_session:
                await session.close()

    @staticmethod
    async def get_all_categories_with_items(conn: AsyncSession) -> list[dict]:
        """Получить все категории вместе с товарами."""
        result = await conn.execute(
            select(Category)
            .options(selectinload(Category.items))
            .where(Category.name != "__SYSTEM__")
            .order_by(Category.sort_order, Category.name)
        )
        categories = result.scalars().all()

        data = []
        for cat in categories:
            items = [
                {
                    "id": item.id,
                    "text": item.text,
                    "serial": item.serial,
                    "is_booked": item.is_booked,
                    "created_at": item.created_at,
                }
                for item in cat.items
            ]
            data.append({
                "id": cat.id,
                "name": cat.name,
                "items": items
            })
        return data

    @staticmethod
    async def get_item_id_by_serial(serial: str, conn: AsyncSession) -> int | None:
        """Получить ID товара по серийному номеру."""
        if not serial:
            return None
        result = await conn.execute(
            select(Item.id).where(func.upper(Item.serial) == serial.strip().upper())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_item_by_serial(serial: str, conn: AsyncSession) -> Item | None:
        result = await conn.execute(
            select(Item).where(func.upper(Item.serial) == serial.strip().upper())
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def delete_item(item_id: int, reason: str = "admin", conn: AsyncSession | None = None) -> bool:
        """Удалить товар (с сохранением в DeletedItem)."""
        own_session = False
        if conn is None:
            from bot.db import get_async_session_factory
            session = get_async_session_factory()()
            own_session = True
        else:
            session = conn

        try:
            if own_session:
                await session.begin()

            item = await session.get(Item, item_id)
            if not item:
                return False

            deleted = DeletedItem(
                item_id=item.id,
                text=item.text,
                serial=item.serial,
                category_id=item.category_id,
                reason=reason
            )
            session.add(deleted)
            await session.delete(item)

            if own_session:
                await session.commit()
            return True

        except Exception:
            if own_session:
                await session.rollback()
            raise
        finally:
            if own_session:
                await session.close()
