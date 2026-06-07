import logging
from typing import Any

from bot.db import get_async_session_factory, get_pool
from bot.models import Category, DeletedItem, Item
from bot.services.cache import cache

logger = logging.getLogger(__name__)

CACHE_KEY = "assortment:inventory"
CACHE_TTL = 300  # 5 минут


class AssortmentService:
    """
    Сервис работы с ассортиментом товаров.

    Отвечает за:
    - Загрузку полного ассортимента (с кэшированием)
    - Удаление товаров по серийному номеру (продажа / бронь / ручное удаление)
    - Полную замену ассортимента (из топика «Ассортимент» или админки)
    - Инвалидацию кэша после изменений
    """

    @staticmethod
    async def load_inventory() -> list[dict[str, Any]]:
        """
        Загружает полный ассортимент с группировкой по категориям.
        Использует Redis-кэш для снижения нагрузки на БД.
        """
        # Пытаемся взять из кэша
        cached = await cache.get(CACHE_KEY)
        if cached is not None:
            logger.debug("Ассортимент загружен из кэша Redis")
            return cached

        try:
            async_session = get_async_session_factory()
            async with async_session() as session:
                # Получаем все категории (кроме системной)
                categories_query = (
                    select(Category)
                    .where(Category.name != "__SYSTEM__")
                    .order_by(Category.sort_order, Category.name)
                )
                categories = (await session.execute(categories_query)).scalars().all()

                result = []
                for category in categories:
                    # Получаем товары категории
                    items_query = (
                        select(Item)
                        .where(Item.category_id == category.id)
                        .order_by(Item.created_at.desc())
                    )
                    items = (await session.execute(items_query)).scalars().all()

                    category_dict = {
                        "id": category.id,
                        "header": category.name,
                        "sort_order": category.sort_order,
                        "items": [
                            {
                                "id": item.id,
                                "text": item.text,
                                "serial": item.serial,
                                "is_booked": item.is_booked,
                                "created_at": item.created_at,
                                "booking_price": float(item.booking_price) if item.booking_price else None,
                                "sale_price": float(item.sale_price) if item.sale_price else None,
                            }
                            for item in items
                        ]
                    }
                    result.append(category_dict)

            # Кэшируем результат
            await cache.set(CACHE_KEY, result, ttl=CACHE_TTL)
            logger.info(f"Ассортимент загружен из БД и закэширован ({len(result)} категорий)")
            return result

        except Exception as e:
            logger.exception(f"Ошибка загрузки ассортимента: {e}")
            return []

    @staticmethod
    async def remove_by_serial(
        serial: str,
        reason: str = "sale",
        conn=None
    ) -> bool:
        """
        Удаляет товар по серийному номеру и создаёт запись в deleted_items.

        Args:
            serial: Серийный номер товара
            reason: Причина удаления ('sale', 'booking', 'admin_manual' и т.д.)
            conn: Опциональное соединение (для использования внутри транзакции)

        Returns:
            True, если товар был успешно удалён
        """
        if not serial:
            return False

        own_conn = False
        if conn is None:
            pool = await get_pool()
            conn = await pool.acquire()
            own_conn = True

        try:
            # Находим товар
            item = await conn.fetchrow(
                "SELECT id, text, serial, category_id FROM items WHERE serial = $1",
                serial.strip().upper()
            )

            if not item:
                logger.warning(f"Попытка удаления несуществующего серийника: {serial}")
                return False

            # Создаём запись об удалении
            await conn.execute(
                """
                INSERT INTO deleted_items 
                    (item_id, text, serial, category_id, reason, sale_message_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                item["id"],
                item["text"],
                item["serial"],
                item["category_id"],
                reason,
                None  # sale_message_id заполняется при продаже из админки
            )

            # Удаляем товар
            await conn.execute("DELETE FROM items WHERE id = $1", item["id"])

            # Инвалидируем кэш
            await AssortmentService.invalidate_cache()

            logger.info(f"✅ Товар удалён: serial={serial}, reason={reason}")
            return True

        except Exception as e:
            logger.exception(f"Ошибка при удалении товара по serial={serial}: {e}")
            return False

        finally:
            if own_conn and conn:
                await conn.close()

    @staticmethod
    async def bulk_replace_assortment(categories: list[dict[str, Any]]) -> bool:
        """
        Полностью заменяет текущий ассортимент на новый.
        Используется при загрузке из топика «Ассортимент».

        Внимание: операция выполняется в транзакции.
        """
        if not categories:
            logger.warning("Попытка замены ассортимента пустым списком")
            return False

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # Удаляем все товары (кроме системного)
                    await conn.execute(
                        "DELETE FROM items WHERE category_id NOT IN "
                        "(SELECT id FROM categories WHERE name = '__SYSTEM__')"
                    )

                    # Удаляем все категории (кроме системной)
                    await conn.execute(
                        "DELETE FROM categories WHERE name != '__SYSTEM__'"
                    )

                    for cat in categories:
                        header = cat.get("header", "").strip()
                        if not header:
                            continue

                        # Создаём категорию
                        cat_id = await conn.fetchval(
                            """
                            INSERT INTO categories (name, sort_order)
                            VALUES ($1, $2)
                            ON CONFLICT (name) DO UPDATE SET sort_order = EXCLUDED.sort_order
                            RETURNING id
                            """,
                            header,
                            cat.get("sort_order", 0)
                        )

                        # Добавляем товары
                        for item in cat.get("items", []):
                            text = item.get("text", "").strip()
                            if not text:
                                continue

                            serial = item.get("serial")
                            if serial:
                                serial = serial.strip().upper()

                            await conn.execute(
                                """
                                INSERT INTO items (text, serial, category_id, is_booked)
                                VALUES ($1, $2, $3, $4)
                                """,
                                text,
                                serial,
                                cat_id,
                                "Бронь от" in text
                            )

                    await AssortmentService.invalidate_cache()
                    logger.info(f"✅ Ассортимент полностью заменён ({len(categories)} категорий)")
                    return True

                except Exception as e:
                    logger.exception(f"Ошибка при bulk_replace_assortment: {e}")
                    raise

    @staticmethod
    async def invalidate_cache() -> None:
        """Инвалидирует кэш ассортимента."""
        try:
            await cache.delete(CACHE_KEY)
            logger.debug("Кэш ассортимента инвалидирован")
        except Exception as e:
            logger.warning(f"Не удалось инвалидировать кэш ассортимента: {e}")
