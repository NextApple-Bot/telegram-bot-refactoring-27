import logging
from typing import List, Dict, Any

from sqlalchemy import select, delete, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory
from bot.models import Category, Item

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом (категории + товары)."""

    @staticmethod
    async def load_inventory() -> List[Dict[str, Any]]:
        """Загружает весь ассортимент с группировкой по категориям.
        Сортировка категорий теперь идёт по sort_order (как задумано).
        """
        async with get_async_session_factory()() as session:
            query = (
                select(Category, Item)
                .outerjoin(Item, Category.id == Item.category_id)
                .order_by(Category.sort_order, Category.name, Item.text)
            )
            result = await session.execute(query)
            rows = result.all()

        # Группировка
        categories: Dict[str, Dict[str, Any]] = {}
        for cat, item in rows:
            cat_name = cat.name.strip()
            if cat_name not in categories:
                categories[cat_name] = {
                    "id": cat.id,
                    "name": cat_name,
                    "sort_order": getattr(cat, 'sort_order', 0),
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

        # Возвращаем в порядке sort_order
        return sorted(
            categories.values(),
            key=lambda x: (x.get("sort_order", 999), x["name"])
        )
