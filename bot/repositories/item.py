import logging
from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from bot.db import get_async_session_factory
from bot.models import Category, DeletedItem, Item

logger = logging.getLogger(__name__)


class ItemRepository:

    # ====================== БАЗОВЫЕ МЕТОДЫ ======================

    @staticmethod
    async def get_all_categories_with_items() -> list[dict[str, Any]]:
        """Возвращает все категории с товарами (для кэширования и вывода)."""
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
        """Возвращает ID категории. Создаёт при необходимости."""
        name = name.strip() or "Без категории:"

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
            category = await session.scalar(
                select(Category).where(func.lower(Category.name) == func.lower(name))
            )
            return category.id if category else 0
        finally:
            if own_session:
                await session.close()

    # ====================== ПОИСК ТОВАРОВ ======================

    @staticmethod
    async def get_item_by_serial(serial: str, conn=None) -> Optional[Item]:
        """Возвращает полный объект товара по серийному номеру."""
        if not serial:
            return None

        normalized = serial.strip().upper()
        own_session = False
        if conn is None:
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True
        else:
            session = conn

        try:
            return await session.scalar(
                select(Item).where(func.upper(Item.serial) == normalized)
            )
        finally:
            if own_session:
                await session.close()

    @staticmethod
    async def get_item_id_by_serial(serial: str, conn=None) -> Optional[int]:
        """Возвращает только ID товара по серийному номеру."""
        item = await ItemRepository.get_item_by_serial(serial, conn=conn)
        return item.id if item else None

    @staticmethod
    async def get_item_by_text(text: str, conn=None) -> Optional[Item]:
        """Ищет товар по точному совпадению текста."""
        if not text:
            return None

        own_session = False
        if conn is None:
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True
        else:
            session = conn

        try:
            return await session.scalar(
                select(Item).where(Item.text == text.strip())
            )
        finally:
            if own_session:
                await session.close()

    # ====================== УДАЛЕНИЕ И ВОССТАНОВЛЕНИЕ ======================

    @staticmethod
    async def remove_by_serial(serial: str, reason: str = "sale", conn=None) -> bool:
        """Удаляет товар по серийному номеру и создаёт запись в deleted_items."""
        if not serial:
            return False

        normalized = serial.strip().upper()
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

            item = await session.scalar(
                select(Item).where(func.upper(Item.serial) == normalized)
            )
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
            logger.exception(f"Ошибка при удалении по serial: {serial}")
            if own_session:
                await session.rollback()
            return False
        finally:
            if own_session:
                await session.close()

    @staticmethod
    async def restore_deleted_item(deleted_item_id: int, conn=None) -> bool:
        """Восстанавливает товар из deleted_items."""
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

            deleted = await session.get(DeletedItem, deleted_item_id)
            if not deleted:
                return False

            new_item = Item(
                text=deleted.text,
                serial=deleted.serial,
                category_id=deleted.category_id,
                is_booked=False
            )
            session.add(new_item)
            await session.delete(deleted)

            if own_session:
                await session.commit()
            return True

        except Exception:
            logger.exception(f"Ошибка восстановления deleted_item {deleted_item_id}")
            if own_session:
                await session.rollback()
            return False
        finally:
            if own_session:
                await session.close()

    # ====================== МАССОВЫЕ ОПЕРАЦИИ ======================

    @staticmethod
    async def bulk_replace_assortment(categories: list[dict]) -> None:
        """Полная замена ассортимента."""
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            await session.execute(delete(Item))
            await session.execute(delete(Category))

            for cat in categories:
                header = cat.get("header") or cat.get("name", "Без категории:")
                new_cat = Category(name=header.strip(), sort_order=cat.get("sort_order", 999))
                session.add(new_cat)
                await session.flush()

                for item_text in cat.get("items", []):
                    session.add(Item(text=item_text.strip(), category_id=new_cat.id))

        logger.info(f"Ассортимент заменён ({len(categories)} категорий)")
