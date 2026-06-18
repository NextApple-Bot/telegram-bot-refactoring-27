import logging
from typing import Any

from bot.db import get_pool
from bot.repositories.item import ItemRepository
from bot.repositories.stats import StatsRepository
from bot.services.assortment import AssortmentService
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class SaleService:
    """
    Сервис обработки продаж из топика Sales.
    Отвечает за поиск товаров по серийным номерам,
    удаление их из ассортимента и сохранение статистики.
    """

    @staticmethod
    async def process_sale(
        content: str,
        chat_id: int,
        message_id: int,
        payments: dict[str, float]
    ) -> dict[str, Any]:

        serials = extract_serials(content)

        # === Случай: сообщение без серийных номеров (аксессуар) ===
        if not serials:
            logger.info(
                f"Сообщение {message_id} не содержит серийных номеров — "
                f"считаем аксессуаром. Платежи сохраняем, статистику продаж — нет."
            )
            return {
                "sold_items": [],
                "not_found": [],
                "is_accessory": True,
                "skip_sale_stats": True,
                "skip_payments": False
            }

        sold_items: list[tuple[int, str]] = []
        not_found: list[str] = []

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                for serial in serials:
                    try:
                        item_id = await ItemRepository.get_item_id_by_serial(serial, conn=conn)

                        if item_id:
                            # Удаляем товар из ассортимента
                            await AssortmentService.remove_by_serial(
                                serial,
                                reason="sale",
                                conn=conn
                            )

                            # Сохраняем статистику продажи
                            await StatsRepository.add_sale(
                                item_id=item_id,
                                count=1,
                                cash=0,
                                terminal=0,
                                qr=0,
                                transfer=0,
                                invoice=0,
                                installment=0,
                                is_accessory=False,
                                message_id=message_id,
                                conn=conn
                            )

                            sold_items.append((item_id, serial))
                            logger.info(f"✅ Продажа: item_id={item_id}, serial={serial}")

                        else:
                            not_found.append(serial)
                            logger.warning(f"❌ Серийный номер не найден в ассортименте: {serial}")

                    except Exception as e:
                        logger.exception(
                            f"Ошибка при обработке серийника {serial} в сообщении {message_id}: {e}"
                        )
                        raise

        if not_found:
            logger.info(
                f"Сообщение {message_id}: продано {len(sold_items)} товаров, "
                f"не найдено {len(not_found)} серийников."
            )

        return {
            "sold_items": sold_items,
            "not_found": not_found,
            "is_accessory": False,
            "skip_sale_stats": False,
            "skip_payments": False
        }
