# bot/services/sale.py
import logging

from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class SaleService:
    @staticmethod
    async def process_sale(content: str, chat_id: int, message_id: int, payments: dict) -> dict:
        from bot.db import get_async_session_factory
        from bot.repositories import ItemRepository
        from bot.repositories.stats import StatsRepository

        serials = list(set(extract_serials(content)))
        is_accessory = (len(serials) == 0)

        if is_accessory:
            logger.info(f"Аксессуар: сохранение только платежей {payments}, продажа не регистрируется.")
            return {
                "sold_items": [],
                "not_found": [],
                "payments": payments,
                "is_accessory": True,
                "skip_sale_stats": True
            }

        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            sold_items = []
            for serial in serials:
                item_id = await ItemRepository.get_item_id_by_serial(serial, conn=session)
                if item_id:
                    sold_items.append((item_id, serial))

            if not sold_items:
                logger.info(f"Серийные номера не найдены: {serials}. Статистика и платежи не сохранены.")
                return {
                    "sold_items": [],
                    "not_found": serials,
                    "payments": payments,
                    "is_accessory": False,
                    "skip_sale_stats": True,
                    "skip_payments": True
                }

            from bot.services.assortment import AssortmentService
            for _item_id, serial in sold_items:
                await AssortmentService.remove_by_serial(serial, reason='sale', conn=session)

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

            not_found = [s for s in serials if s not in [x[1] for x in sold_items]]

            return {
                "sold_items": sold_items,
                "not_found": not_found,
                "payments": payments,
                "is_accessory": False,
                "skip_sale_stats": False,
                "skip_payments": False
            }
