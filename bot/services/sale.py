import logging
from typing import Any

from aiogram import Bot

from bot import config
from bot.db import get_async_session_factory, get_pool
from bot.repositories.item import ItemRepository
from bot.repositories.stats import StatsRepository
from bot.services.assortment import AssortmentService
from bot.services.notifications import send_sale_notification
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


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

        # === Случай: аксессуар (без серийников) ===
        if not serials:
            logger.info(
                f"Сообщение {message_id} не содержит серийных номеров — "
                f"считаем аксессуаром."
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
                            # Получаем название товара
                            item = await ItemRepository.get_item_by_id(item_id, conn=conn)
                            item_text = item.text if item else f"Товар #{item_id}"

                            # Удаляем товар из ассортимента
                            await AssortmentService.remove_by_serial(
                                serial,
                                reason="sale",
                                conn=conn
                            )

                            # Сохраняем статистику
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

                            # === Отправка уведомления о продаже ===
                            try:
                                bot = Bot(token=config.BOT_TOKEN)
                                await send_sale_notification(
                                    bot=bot,
                                    item_text=item_text,
                                    price=0,  # цену можно позже передавать из парсинга
                                    payment_type="cash",  # можно улучшить
                                    payment_amount=0,
                                )
                            except Exception as notify_err:
                                logger.error(f"Ошибка отправки уведомления о продаже: {notify_err}")

                        else:
                            not_found.append(serial)
                            logger.warning(f"❌ Серийный номер не найден: {serial}")

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
