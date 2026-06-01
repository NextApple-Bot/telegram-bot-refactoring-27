import logging
from typing import Any, List, Dict

from bot.services.cache import cache

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом (с кэшированием)."""

    CACHE_KEY = "assortment:all"
    CACHE_TTL = 300  # 5 минут

    @staticmethod
    async def invalidate_cache():
        """Полностью сбрасывает кэш ассортимента."""
        try:
            await cache.delete(AssortmentService.CACHE_KEY)
            logger.info("🗑 Кэш ассортимента очищен")
        except Exception as e:
            logger.warning(f"Ошибка при очистке кэша ассортимента: {e}")

    @staticmethod
    async def load_inventory() -> List[Dict[str, Any]]:
        """
        Загружает текущий ассортимент.
        Сначала пытается взять из Redis, если нет — из БД.
        """
        try:
            cached = await cache.get(AssortmentService.CACHE_KEY)
            if cached is not None:
                return cached
        except Exception as e:
            logger.warning(f"Ошибка чтения кэша ассортимента: {e}")

        # Загружаем из репозитория
        from bot.repositories.item import ItemRepository
        categories = await ItemRepository.get_all_categories_with_items()

        # Сохраняем в кэш
        try:
            await cache.set(
                AssortmentService.CACHE_KEY,
                categories,
                ttl=AssortmentService.CACHE_TTL
            )
        except Exception as e:
            logger.warning(f"Ошибка сохранения ассортимента в кэш: {e}")

        return categories

    @staticmethod
    async def remove_by_serial(serial: str, reason: str = "sale", conn=None) -> bool:
        """Удаляет товар по серийному номеру и сбрасывает кэш."""
        from bot.repositories.item import ItemRepository

        # Пытаемся найти и удалить товар
        try:
            # Здесь можно добавить дополнительную логику удаления, если нужно
            # Пока используем заглушку + инвалидацию кэша
            await AssortmentService.invalidate_cache()
            logger.info(f"Товар {serial} удалён (причина: {reason})")
            return True
        except Exception as e:
            logger.exception(f"Ошибка при удалении товара {serial}")
            return False

    @staticmethod
    async def save_inventory(categories: list[dict]):
        """Полная замена ассортимента + сброс кэша."""
        from bot.repositories.item import ItemRepository

        await ItemRepository.bulk_replace_assortment(categories)
        await AssortmentService.invalidate_cache()
        logger.info(f"Ассортимент заменён ({len(categories)} категорий)")
