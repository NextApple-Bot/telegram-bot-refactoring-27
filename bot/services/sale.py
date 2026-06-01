import logging
from typing import Any

from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class SaleService:

    @staticmethod
    async def process_sale(
        content: str,
        chat_id: int,
        message_id: int,
        payments: dict
    ) -> dict[str, Any]:

        from bot.db import get_async_session_factory
        from bot.repositories import ItemRepository
        from bot.repositories.stats import StatsRepository
        from bot.services.assortment import AssortmentService

        serials = list(set(extract_serials(content)))
        is_accessory = len(serials) == 0

        if is_accessory:
            logger.info("Аксессуар: сохраняем только платежи, статистику продаж не обновляем.")
            return {
                "sold_items": [],
                "not_found": [],
                "payments": payments,
                "is_accessory": True,
                "skip_sale_stats": True,
                "skip_payments": False
            }

        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            sold_items = []
            failed_to_remove = []

            for serial in serials:
                try:
                    item_id = await ItemRepository.get_item_id_by_serial(serial, conn=session)

                    if not item_id:
                        logger.warning(f"Товар с серийным номером {serial} не найден в ассортименте.")
                        continue

                    # Пытаемся удалить товар
                    removed = await AssortmentService.remove_by_serial(
                        serial, reason='sale', conn=session
                    )

                    if removed:
                        sold_items.append((item_id, serial))
                        logger.info(f"Товар продан и удалён из ассортимента: {serial}")
                    else:
                        failed_to_remove.append(serial)
                        logger.warning(f"Не удалось удалить товар {serial} из ассортимента.")

                except Exception as e:
                    logger.exception(f"Ошибка при обработке серийного номера {serial}")
                    failed_to_remove.append(serial)

            # Если ничего не удалось продать
            if not sold_items:
                logger.info(f"Ни один товар не был продан. Серийники: {serials}")
                return {
                    "sold_items": [],
                    "not_found": serials,
                    "payments": payments,
                    "is_accessory": False,
                    "skip_sale_stats": True,
                    "skip_payments": True
                }

            # Сохраняем статистику только по успешно проданным товарам
            try:
                await StatsRepository.add_sale(
                    count=len(sold_items),
                    cash=payments.get('cash', 0),
                    terminal=payments.get('terminal', 0),
                    qr=payments.get('qr', 0),
                    transfer=payments.get('transfer', 0),
                    invoice=payments.get('invoice', 0),
                    installment=payments.get('installment', 0),
                    is_accessory=False,
                    message_id=message_id,
                    conn=session
                )
            except Exception as e:
                logger.exception("Ошибка при сохранении статистики продажи")
                # Можно решить: откатывать транзакцию или нет. Пока продолжаем.

            not_found = [s for s in serials if s not in [x[1] for x in sold_items]]

            logger.info(f"Успешно обработано продаж: {len(sold_items)}. Не найдено: {len(not_found)}")

            return {
                "sold_items": sold_items,
                "not_found": not_found,
                "payments": payments,
                "is_accessory": False,
                "skip_sale_stats": False,
                "skip_payments": False
            }
