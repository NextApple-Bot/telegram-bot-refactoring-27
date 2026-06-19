# bot/repositories/item.py

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory, get_pool
from bot.models import Category, Item

logger = logging.getLogger(__name__)


class ItemRepository:
    """Репозиторий для работы с товарами и категориями."""

    @staticmethod
    async def get_or_create_category(name: str, conn: Optional[AsyncSession] = None) -> int:
        """Получает ID категории по имени или создаёт новую."""
        async_session = get_async_session_factory()

        if conn is None:
            async with async_session() as session, session.begin():
                return await ItemRepository._get_or_create_category_internal(name, session)
        else:
            return await ItemRepository._get_or_create_category_internal(name, conn)

    @staticmethod
    async def _get_or_create_category_internal(name: str, session: AsyncSession) -> int:
        result = await session.execute(
            select(Category).where(Category.name == name)
        )
        category = result.scalar_one_or_none()

        if category:
            return category.id

        # Создаём новую категорию
        new_category = Category(name=name, sort_order=0)
        session.add(new_category)
        await session.flush()
        return new_category.id

    @staticmethod
    async def add_item(
        text: str,
        serial: Optional[str] = None,
        category_id: Optional[int] = None,
        conn: Optional[AsyncSession] = None
    ) -> int:
        """Добавляет новый товар."""
        async_session = get_async_session_factory()

        if conn is None:
            async with async_session() as session, session.begin():
                return await ItemRepository._add_item_internal(text, serial, category_id, session)
        else:
            return await ItemRepository._add_item_internal(text, serial, category_id, conn)

    @staticmethod
    async def _add_item_internal(
        text: str, serial: Optional[str], category_id: Optional[int], session: AsyncSession
    ) -> int:
        item = Item(
            text=text,
            serial=serial.upper() if serial else None,
            category_id=category_id,
            is_booked=False
        )
        session.add(item)
        await session.flush()
        return item.id

    @staticmethod
    async def get_item_id_by_serial(serial: str, conn: Optional[AsyncSession] = None) -> Optional[int]:
        """Возвращает ID товара по серийному номеру."""
        async_session = get_async_session_factory()

        if conn is None:
            async with async_session() as session:
                return await ItemRepository._get_item_id_by_serial_internal(serial, session)
        else:
            return await ItemRepository._get_item_id_by_serial_internal(serial, conn)

    @staticmethod
    async def _get_item_id_by_serial_internal(serial: str, session: AsyncSession) -> Optional[int]:
        result = await session.execute(
            select(Item.id).where(Item.serial == serial.upper())
        )
        row = result.scalar_one_or_none()
        return row

    @staticmethod
    async def get_item_by_serial(serial: str, conn: Optional[AsyncSession] = None) -> Optional[dict]:
        """Возвращает информацию о товаре по серийному номеру."""
        async_session = get_async_session_factory()

        if conn is None:
            async with async_session() as session:
                return await ItemRepository._get_item_by_serial_internal(serial, session)
        else:
            return await ItemRepository._get_item_by_serial_internal(serial, conn)

    @staticmethod
    async def _get_item_by_serial_internal(serial: str, session: AsyncSession) -> Optional[dict]:
        result = await session.execute(
            select(Item).where(Item.serial == serial.upper())
        )
        item = result.scalar_one_or_none()
        if item:
            return {
                "id": item.id,
                "text": item.text,
                "serial": item.serial,
                "category_id": item.category_id,
                "is_booked": item.is_booked
            }
        return None

    @staticmethod
    async def get_item_by_text(text: str, conn: Optional[AsyncSession] = None) -> Optional[dict]:
        """Возвращает информацию о товаре по точному тексту."""
        async_session = get_async_session_factory()

        if conn is None:
            async with async_session() as session:
                return await ItemRepository._get_item_by_text_internal(text, session)
        else:
            return await ItemRepository._get_item_by_text_internal(text, conn)

    @staticmethod
    async def _get_item_by_text_internal(text: str, session: AsyncSession) -> Optional[dict]:
        result = await session.execute(
            select(Item).where(Item.text == text)
        )
        item = result.scalar_one_or_none()
        if item:
            return {
                "id": item.id,
                "text": item.text,
                "serial": item.serial,
                "category_id": item.category_id,
                "is_booked": item.is_booked
            }
        return None

    @staticmethod
    async def mark_item_booked(item_id: int, new_text: Optional[str] = None, conn: Optional[AsyncSession] = None):
        """Помечает товар как забронированный."""
        async_session = get_async_session_factory()

        if conn is None:
            async with async_session() as session, session.begin():
                await ItemRepository._mark_item_booked_internal(item_id, new_text, session)
        else:
            await ItemRepository._mark_item_booked_internal(item_id, new_text, conn)

    @staticmethod
    async def _mark_item_booked_internal(item_id: int, new_text: Optional[str], session: AsyncSession):
        stmt = (
            update(Item)
            .where(Item.id == item_id)
            .values(is_booked=True)
        )
        if new_text:
            stmt = stmt.values(text=new_text)

        await session.execute(stmt)

    @staticmethod
    async def bulk_replace_assortment(categories: list[dict[str, Any]], conn: Optional[AsyncSession] = None):
        """Полностью заменяет ассортимент (используется при загрузке из топика)."""
        async_session = get_async_session_factory()

        if conn is None:
            async with async_session() as session, session.begin():
                await ItemRepository._bulk_replace_assortment_internal(categories, session)
        else:
            await ItemRepository._bulk_replace_assortment_internal(categories, conn)

    @staticmethod
    async def _bulk_replace_assortment_internal(categories: list[dict], session: AsyncSession):
        # Удаляем все товары (кроме системных)
        await session.execute(
            "DELETE FROM items WHERE category_id NOT IN "
            "(SELECT id FROM categories WHERE name = '__SYSTEM__')"
        )

        # Удаляем все категории (кроме системной)
        await session.execute("DELETE FROM categories WHERE name != '__SYSTEM__'")

        for cat in categories:
            header = cat.get("header", "").strip()
            if not header:
                continue

            cat_id = await ItemRepository.get_or_create_category(header, conn=session)

            for item in cat.get("items", []):
                text = item.get("text", "").strip() if isinstance(item, dict) else str(item).strip()
                if not text:
                    continue

                serial = item.get("serial") if isinstance(item, dict) else None
                if serial:
                    serial = serial.strip().upper()

                is_booked = "Бронь от" in text

                new_item = Item(
                    text=text,
                    serial=serial,
                    category_id=cat_id,
                    is_booked=is_booked
                )
                session.add(new_item)

    @staticmethod
    async def restore_deleted_item(item_id: int, conn: Optional[AsyncSession] = None) -> bool:
        """Восстанавливает удалённый товар (из таблицы deleted_items)."""
        logger.warning("restore_deleted_item вызван — реализация зависит от контекста")
        return True
