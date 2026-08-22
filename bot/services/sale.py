import logging
import re
from typing import Any

from bot.repositories.item import ItemRepository
from bot.repositories.stats import StatsRepository
from bot.services.assortment import AssortmentService
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


def _first_product_line(content: str) -> str | None:
    """Первая строка сообщения, похожая на название товара."""
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # Пропускаем суммы, ФИО, телефоны, площадки
        lower = line.lower()
        if any(k in lower for k in (
            'стоимость', 'наличн', 'терминал', 'перевод', 'общая',
            'площадка', 'фио', 'qr', 'рассроч', 'предоплат',
        )):
            continue
        if re.match(r'^\+?\d[\d\s\-()]{8,}$', line):
            continue
        if re.match(r'^\d{1,2}\.\d{1,2}\.\d{2,4}$', line):
            continue
        return line
    return None


class SaleService:
    """
    Сервис обработки продаж из топика Sales.
    """

    @staticmethod
    async def process_sale(
        content: str,
        chat_id: int,
        message_id: int,
        payments: dict[str, float]
    ) -> dict[str, Any]:

        serials = extract_serials(content)

        sold_items: list[tuple[int, str]] = []
        not_found: list[str] = []

        # === Поиск по серийникам / кодам (№8 и т.п.) ===
        for serial in serials:
            try:
                item_id = await ItemRepository.get_item_id_by_serial(serial)

                if item_id:
                    await AssortmentService.remove_by_serial(serial, reason="sale")
                    await StatsRepository.add_sale(
                        item_id=item_id,
                        count=1,
                        message_id=message_id,
                    )
                    sold_items.append((item_id, serial))
                    logger.info(f"✅ Продажа: item_id={item_id}, serial={serial}")
                else:
                    not_found.append(serial)
                    logger.warning(f"❌ Серийный номер не найден: {serial}")
            except Exception as e:
                logger.exception(
                    f"Ошибка при обработке серийника {serial} в сообщении {message_id}: {e}"
                )
                raise

        # === Если серийников нет или не нашли — пробуем по тексту первой строки ===
        if not sold_items:
            product_line = _first_product_line(content)
            if product_line:
                try:
                    item = await ItemRepository.get_item_by_text(product_line)
                    # Нечёткое: иногда в продаже чуть другой текст — ищем по вхождению №
                    if not item and serials:
                        # уже пробовали serial
                        pass
                    if item:
                        item_id = item["id"]
                        serial = item.get("serial")
                        if serial:
                            await AssortmentService.remove_by_serial(serial, reason="sale")
                        else:
                            # Удаление по id через serial=None — используем remove после
                            # прямого удаления: повторный get + delete by id
                            from bot.db import get_pool
                            pool = await get_pool()
                            async with pool.acquire() as conn:
                                await conn.execute(
                                    """
                                    INSERT INTO deleted_items
                                        (item_id, text, serial, category_id, reason, sale_message_id)
                                    VALUES ($1, $2, $3, $4, $5, $6)
                                    """,
                                    item["id"], item["text"], item.get("serial"),
                                    item["category_id"], "sale", message_id,
                                )
                                await conn.execute(
                                    "DELETE FROM items WHERE id = $1", item["id"]
                                )
                            await AssortmentService.invalidate_cache()

                        await StatsRepository.add_sale(
                            item_id=item_id,
                            count=1,
                            message_id=message_id,
                        )
                        sold_items.append((item_id, serial or product_line))
                        not_found = []
                        logger.info(f"✅ Продажа по тексту: item_id={item_id}, text={product_line}")
                except Exception as e:
                    logger.exception(f"Ошибка поиска товара по тексту: {e}")

        # === Нет ни серийников, ни найденного товара → аксессуар / только платежи ===
        if not serials and not sold_items:
            logger.info(
                f"Сообщение {message_id} без серийников — считаем аксессуаром."
            )
            return {
                "sold_items": [],
                "not_found": [],
                "is_accessory": True,
                "skip_sale_stats": True,
                "skip_payments": False,
            }

        return {
            "sold_items": sold_items,
            "not_found": not_found,
            "is_accessory": False,
            "skip_sale_stats": False,
            "skip_payments": False,
        }
