import logging
from typing import Any

from bot.db import get_async_session_factory
from bot.models import DeletedItem, Item
from bot.services.cache import cache

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом + кэширование."""

    CACHE_KEY = "assortment:all"
    CACHE_TTL = 300  # 5 минут

    @staticmethod
    async def invalidate_cache():
        """Полностью очищает кэш ассортимента."""
        try:
            await cache.delete(AssortmentService.CACHE_KEY)
            logger.info("🗑 Кэш ассортимента полностью очищен")
        except Exception as e:
            logger.warning(f"Не удалось очистить кэш ассортимента: {e}")

    @staticmethod
    async def load_inventory() -> list[dict[str, Any]]:
        """
        Загружает ассортимент.
        Сначала пытается взять из кэша, если нет — грузит из БД и кэширует.
        """
        try:
            cached = await cache.get(AssortmentService.CACHE_KEY)
            if cached is not None:
                logger.debug("Ассортимент взят из кэша")
                return cached
        except Exception as e:
            logger.warning(f"Ошибка чтения кэша ассортимента: {e}")

        # Если кэша нет — грузим из репозитория
        from bot.repositories.item import ItemRepository
        categories = await ItemRepository.get_all_categories_with_items()

        # Сохраняем в кэш
        try:
            await cache.set(
                AssortmentService.CACHE_KEY,
                categories,
                ttl=AssortmentService.CACHE_TTL
            )
            logger.debug("Ассортимент сохранён в кэш")
        except Exception as e:
            logger.warning(f"Не удалось сохранить ассортимент в кэш: {e}")

        return categories

    @staticmethod
    async def remove_by_serial(serial: str, reason: str = 'sale', conn=None) -> bool:
        """Удаляет товар по серийному номеру и инвалидирует кэш."""
        from bot.repositories.item import ItemRepository

        result = await ItemRepository.remove_by_serial(serial, reason=reason, conn=conn)

        if result:
            await AssortmentService.invalidate_cache()

        return result

    @staticmethod
    async def save_inventory(categories: list[dict]):
        """Полностью заменяет ассортимент и сбрасывает кэш."""
        from bot.repositories.item import ItemRepository

        await ItemRepository.bulk_replace_assortment(categories)
        await AssortmentService.invalidate_cache()
        logger.info("Ассортимент полностью заменён + кэш сброшен")
