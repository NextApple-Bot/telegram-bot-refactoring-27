import logging
from datetime import date

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Item
from bot.repositories.item import ItemRepository
from bot.services.cache import cache

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом."""

    @staticmethod
    async def remove_by_serial(serial: str, reason: str = "sale", conn: AsyncSession | None = None) -> bool:
        """Удалить товар по серийному номеру (при продаже)."""
        if not serial:
            return False

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

            item = await ItemRepository.get_item_by_serial(serial, session)
            if not item:
                logger.warning(f"Товар с серийным {serial} не найден для удаления")
                return False

            deleted = await ItemRepository.delete_item(item.id, reason=reason, conn=session)
            
            if own_session:
                await session.commit()

            await AssortmentService.invalidate_cache()
            logger.info(f"Товар {serial} удалён (причина: {reason})")
            return deleted

        except Exception as e:
            if own_session:
                await session.rollback()
            logger.exception(f"Ошибка при удалении товара {serial}")
            raise
        finally:
            if own_session:
                await session.close()

    @staticmethod
    async def invalidate_cache() -> None:
        """Сбросить кэш ассортимента."""
        try:
            await cache.delete("assortment:all")
            await cache.delete_pattern("assortment:category:*")
            logger.info("Кэш ассортимента сброшен")
        except Exception as e:
            logger.warning(f"Не удалось сбросить кэш ассортимента: {e}")

    @staticmethod
    async def load_inventory() -> list[dict]:
        """Загрузить весь ассортимент (с кэшированием)."""
        cache_key = "assortment:all"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        from bot.db import get_async_session_factory
        async with get_async_session_factory()() as session:
            data = await ItemRepository.get_all_categories_with_items(session)

        await cache.set(cache_key, data, ttl=300)
        return data

    @staticmethod
    async def get_item_by_serial(serial: str) -> dict | None:
        from bot.db import get_async_session_factory
        async with get_async_session_factory()() as session:
            item = await ItemRepository.get_item_by_serial(serial, session)
            if item:
                return {
                    "id": item.id,
                    "text": item.text,
                    "serial": item.serial,
                    "category_id": item.category_id,
                    "is_booked": item.is_booked,
                }
        return None
