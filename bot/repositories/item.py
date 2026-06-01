import logging
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from bot.db import get_async_session_factory
from bot.models import Category, DeletedItem, Item

logger = logging.getLogger(__name__)


class ItemRepository:

    @staticmethod
    async def get_all_categories_with_items() -> list[dict[str, Any]]:
        """
        Возвращает все категории с товарами.
        Используется в AssortmentService.load_inventory() + кэшировании.
        """
        async_session = get_async_session_factory()
        async with async_session() as session:
            query = (
                select(Category)
                .options(selectinload(Category.items))
                .order_by(Category.sort_order.asc(), Category.name.asc())
            )
            result = await session.execute(query)
            categories = result.scalars().all()

        output = []
        for category in categories:
            if not category.items:
                continue

            items_list = [item.text.strip() for item in category.items]

            output.append({
                "id": category.id,
                "header": category.name.strip(),
                "sort_order": getattr(category, "sort_order", 999),
                "items": items_list
            })

        return output

    @staticmethod
    async def get_or_create_category(name: str, conn=None) -> int:
        """Возвращает ID категории. Если не существует — создаёт."""
        name = name.strip()
        if not name:
            name = "Без категории:"

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

            category = await session.scalar(
                select(Category).where(func.lower(Category.name) == func.lower(name))
            )

            if category:
                return category.id

            # Создаём новую категорию
            max_order = await session.scalar(
                select(func.coalesce(func.max(Category.sort_order), 0))
            )
            new_category = Category(name=name, sort_order=max_order + 1)
            session.add(new_category)
            await session.flush()

            if own_session:
                await session.commit()

            return new_category.id

        except IntegrityError:
            if own_session:
                await session.rollback()
            # На случай гонки — пробуем ещё раз найти
            category = await session.scalar(
                select(Category).where(func.lower(Category.name) == func.lower(name))
            )
            return category.id if category else 0
        finally:
            if own_session:
                await session.close()

    @staticmethod
    async def bulk_replace_assortment(categories: list[dict]) -> None:
        """Полностью заменяет ассортимент (используется при загрузке из топика Ассортимент)."""
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            # Удаляем все товары
            await session.execute(delete(Item))
            # Удаляем все категории (кроме системных при необходимости)
            await session.execute(delete(Category))

            for cat in categories:
                header = cat.get("header") or cat.get("name", "Без категории:")
                new_category = Category(name=header.strip(), sort_order=cat.get("sort_order", 999))
                session.add(new_category)
                await session.flush()

                for item_text in cat.get("items", []):
                    session.add(Item(text=item_text.strip(), category_id=new_category.id))

        logger.info(f"Ассортимент полностью заменён ({len(categories)} категорий)")

    @staticmethod
    async def remove_by_serial(serial: str, reason: str = "sale", conn=None) -> bool:
        """Удаляет товар по серий
