# bot/services/assortment.py
import logging

from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import DeletedItem, Item
from bot.services.cache import cache

logger = logging.getLogger(__name__)


class AssortmentService:
    """Сервис для работы с ассортиментом (объединённая версия v26 + v27)."""

    CACHE_KEY = "assortment:all"
    CACHE_TTL = 300  # 5 минут — оптимально для производства

    @classmethod
    async def invalidate_cache(cls):
        """Сброс кэша ассортимента."""
        try:
            await cache.delete(cls.CACHE_KEY)
            logger.debug("Кэш ассортимента успешно инвалидирован")
        except Exception as e:
            logger.warning(f"Не удалось инвалидировать кэш ассортимента: {e}")

    @classmethod
    async def load_inventory(cls) -> list[dict[str, list[str]]]:
        """Загружает актуальный ассортимент (с кэшем)."""
        try:
            cached = await cache.get(cls.CACHE_KEY)
            if cached is not None:
                logger.debug("Ассортимент загружен из Redis")
                return cached
        except Exception as e:
            logger.warning(f"Ошибка чтения кэша ассортимента: {e}")

        # Если в кэше ничего нет — загружаем из БД
        from bot.repositories.item import ItemRepository
        try:
            categories = await ItemRepository.get_all_categories_with_items()
            # Сохраняем в кэш
            await cache.set(cls.CACHE_KEY, categories, ttl=cls.CACHE_TTL)
            logger.info(f"Ассортимент загружен из БД ({len(categories)} категорий)")
            return categories
        except Exception as e:
            logger.exception("Критическая ошибка при загрузке ассортимента из БД")
            return []

    @classmethod
    async def save_inventory(cls, categories: list[dict[str, list[str]]]):
        """Сохраняет новый ассортимент (полная замена)."""
        from bot.repositories.item import ItemRepository
        try:
            await ItemRepository.bulk_replace_assortment(categories)
            await cls.invalidate_cache()
            logger.info(f"Ассортимент успешно сохранён ({len(categories)} категорий)")
        except Exception as e:
            logger.exception("Ошибка при сохранении ассортимента")
            raise

    @classmethod
    async def remove_by_serial(cls, serial: str, reason: str = "sale", conn=None) -> int:
        """Удаляет товар по серийному номеру и создаёт запись в DeletedItem."""
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
            logger.info(f"Товар удалён по серийному номеру: {serial} (причина: {reason})")
            return 1

        except Exception as e:
            if own_session:
                await session.rollback()
            logger.exception(f"Ошибка при удалении товара по серийному номеру {serial}")
            return 0
        finally:
            if own_session:
                await session.close()
