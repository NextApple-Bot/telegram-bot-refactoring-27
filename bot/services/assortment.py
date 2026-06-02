import logging
from typing import Any, List, Dict

from bot.services.cache import cache

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом."""

    CACHE_KEY = "assortment:all"
    CACHE_TTL = 300

    @staticmethod
    async def invalidate_cache():
        try:
            await cache.delete(AssortmentService.CACHE_KEY)
            logger.info("🗑 Кэш ассортимента очищен")
        except Exception as e:
            logger.warning(f"Ошибка очистки кэша: {e}")

    @staticmethod
    async def load_inventory() -> List[Dict[str, Any]]:
        try:
            cached = await cache.get(AssortmentService.CACHE_KEY)
            if cached is not None:
                return cached
        except Exception:
            pass

        from bot.repositories.item import ItemRepository
        categories = await ItemRepository.get_all_categories_with_items()

        try:
            await cache.set(AssortmentService.CACHE_KEY, categories, ttl=AssortmentService.CACHE_TTL)
        except Exception:
            pass

        return categories

    @staticmethod
    async def remove_by_serial(serial: str, reason: str = "sale", conn=None) -> bool:
        from bot.repositories.item import ItemRepository
        from bot.db import get_async_session_factory
        from bot.models import DeletedItem, Item
        from sqlalchemy import select, func

        normalized = serial.strip().upper()
        async_session = get_async_session_factory()

        if conn is not None:
            session = conn
            own = False
        else:
            session = async_session()
            own = True

        try:
            if own:
                await session.begin()

            item = (await session.execute(
                select(Item).where(func.upper(Item.serial) == normalized)
            )).scalar_one_or_none()

            if item:
                session.add(DeletedItem(
                    item_id=item.id,
                    text=item.text,
                    serial=item.serial,
                    category_id=item.category_id,
                    reason=reason
                ))
                await session.delete(item)
                await AssortmentService.invalidate_cache()
                if own:
                    await session.commit()
                return True

            if own:
                await session.commit()
            return False

        except Exception as e:
            if own:
                await session.rollback()
            logger.exception(f"Ошибка удаления товара {serial}")
            return False
        finally:
            if own:
                await session.close()

    @staticmethod
    async def save_inventory(categories: list[dict]):
        from bot.repositories.item import ItemRepository
        await ItemRepository.bulk_replace_assortment(categories)
        await AssortmentService.invalidate_cache()
