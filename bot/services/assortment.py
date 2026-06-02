import logging

from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import DeletedItem, Item
from bot.services.cache import cache

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом (восстановленная версия)."""

    CACHE_KEY = "assortment:all"
    CACHE_TTL = 300

    @classmethod
    async def invalidate_cache(cls):
        try:
            await cache.delete(cls.CACHE_KEY)
            logger.info("Кэш ассортимента сброшен")
        except Exception as e:
            logger.warning(f"Не удалось сбросить кэш: {e}")

    @classmethod
    async def load_inventory(cls) -> list[dict]:
        try:
            cached = await cache.get(cls.CACHE_KEY)
            if cached is not None:
                return cached
        except Exception:
            pass

        from bot.repositories.item import ItemRepository
        categories = await ItemRepository.get_all_categories_with_items()

        try:
            await cache.set(cls.CACHE_KEY, categories, ttl=cls.CACHE_TTL)
        except Exception:
            pass

        return categories

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = "sale", conn=None) -> int:
        """Удалить товар по серийному номеру."""
        if not serial:
            return 0

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

            result = await session.execute(
                select(Item).where(func.upper(Item.serial) == normalized)
            )
            item = result.scalar_one_or_none()

            if not item:
                return 0

            # Создаём запись об удалении
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

            await cls.invalidate_cache()
            logger.info(f"Товар {serial} удалён (причина: {reason})")
            return 1

        except Exception as e:
            if own_session:
                await session.rollback()
            logger.exception(f"Ошибка удаления товара {serial}")
            return 0
        finally:
            if own_session:
                await session.close()
