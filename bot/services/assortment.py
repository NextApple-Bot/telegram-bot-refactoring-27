import logging
from typing import List, Dict, Any

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory
from bot.models import Category, DeletedItem, Item

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом (категории + товары)."""

    @staticmethod
    async def load_inventory() -> List[Dict[str, Any]]:
        """Загружает весь ассортимент с группировкой по категориям."""
        async with get_async_session_factory()() as session:
            query = (
                select(Category, Item)
                .outerjoin(Item, Category.id == Item.category_id)
                .order_by(Category.sort_order, Category.name, Item.text)
            )
            result = await session.execute(query)
            rows = result.all()

        categories: Dict[str, Dict[str, Any]] = {}
        for cat, item in rows:
            cat_name = cat.name.strip()
            if cat_name not in categories:
                categories[cat_name] = {
                    "id": cat.id,
                    "name": cat_name,
                    "sort_order": getattr(cat, 'sort_order', 999),
                    "items": []
                }

            if item:
                categories[cat_name]["items"].append({
                    "id": item.id,
                    "text": item.text.strip(),
                    "price": getattr(item, 'booking_price', None) or getattr(item, 'sale_price', None),
                    "is_booked": item.is_booked,
                    "serial": item.serial,
                })

        return sorted(
            categories.values(),
            key=lambda x: (x.get("sort_order", 999), x["name"])
        )

    @staticmethod
    async def remove_by_serial(serial: str, reason: str = 'sale', conn=None) -> bool:
        """
        Удаляет товар по серийному номеру.
        Создаёт запись в DeletedItem и удаляет из таблицы items.
        """
        if not serial:
            return False

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
                select(Item).where(Item.serial == serial)
            )

            if not item:
                logger.warning(f"Товар с serial {serial} не найден для удаления")
                return False

            # Создаём запись в архиве
            deleted = DeletedItem(
                item_id=item.id,
                text=item.text,
                serial=item.serial,
                category_id=item.category_id,
                reason=reason
            )
            session.add(deleted)

            # Удаляем из активного ассортимента
            await session.delete(item)

            if own_session:
                await session.commit()

            logger.info(f"Товар {serial} удалён (причина: {reason})")
            return True

        except Exception as e:
            logger.exception(f"Ошибка при удалении товара по serial {serial}")
            if own_session:
                await session.rollback()
            return False
        finally:
            if own_session:
                await session.close()

    # ... остальные методы (import_arrival_from_txt, import_arrival_from_excel и т.д.) остаются без изменений
