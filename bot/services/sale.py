import logging
import re
from typing import Any

from bot.db import get_async_session_factory
from bot.repositories.item import ItemRepository
from bot.services.finalize_sale import (
    finalize_item_sale,
    invalidate_sale_caches,
    unique_sale_message_id,
)
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


def _first_product_line(content: str) -> str | None:
    """Первая строка сообщения, похожая на название товара."""
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(
            k in lower
            for k in (
                "стоимость",
                "наличн",
                "терминал",
                "перевод",
                "общая",
                "площадка",
                "фио",
                "qr",
                "рассроч",
                "предоплат",
            )
        ):
            continue
        if re.match(r"^\+?\d[\d\s\-()]{8,}$", line):
            continue
        if re.match(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$", line):
            continue
        return line
    return None


class SaleService:
    """
    Обработка продаж из топика Sales.
    Запись в БД — через единый finalize_item_sale.
    """

    @staticmethod
    async def process_sale(
        content: str,
        chat_id: int,
        message_id: int,
        payments: dict[str, float],
    ) -> dict[str, Any]:
        serials = extract_serials(content)

        found: list[dict[str, Any]] = []
        not_found: list[str] = []

        for serial in serials:
            try:
                item = await ItemRepository.get_item_by_serial(serial)
                if item:
                    found.append(item)
                    logger.info(
                        "Найден товар serial=%s item_id=%s",
                        serial,
                        item["id"],
                    )
                else:
                    not_found.append(serial)
                    logger.warning("Серийный номер не найден: %s", serial)
            except Exception:
                logger.exception(
                    "Ошибка поиска SN %s в msg=%s", serial, message_id
                )
                raise

        if not found:
            product_line = _first_product_line(content)
            if product_line:
                try:
                    item = await ItemRepository.get_item_by_text(product_line)
                    if item:
                        found.append(item)
                        not_found = []
                        logger.info(
                            "Найден товар по тексту item_id=%s text=%s",
                            item["id"],
                            product_line[:80],
                        )
                except Exception:
                    logger.exception("Ошибка поиска товара по тексту")

        if not serials and not found:
            logger.info(
                "Сообщение %s без серийников — аксессуар / только платежи",
                message_id,
            )
            return {
                "sold_items": [],
                "not_found": [],
                "is_accessory": True,
                "skip_sale_stats": True,
                "skip_payments": False,
                "payments_written": False,
            }

        if not found:
            return {
                "sold_items": [],
                "not_found": not_found,
                "is_accessory": False,
                "skip_sale_stats": False,
                "skip_payments": True,
                "payments_written": False,
            }

        sold_items: list[tuple[int, str]] = []
        async_session = get_async_session_factory()
        async with async_session() as session:
            async with session.begin():
                for idx, item in enumerate(found):
                    msg_id = unique_sale_message_id(message_id, idx)
                    write_pay = idx == 0
                    await finalize_item_sale(
                        session,
                        item_id=item["id"],
                        item_text=item.get("text") or "",
                        item_serial=item.get("serial"),
                        category_id=item.get("category_id"),
                        message_id=msg_id,
                        payments=payments if write_pay else None,
                        reason="sale",
                        is_accessory=False,
                        delete_item=True,
                        write_payments=write_pay,
                    )
                    label = item.get("serial") or item.get("text") or str(item["id"])
                    sold_items.append((item["id"], label))

        await invalidate_sale_caches()

        return {
            "sold_items": sold_items,
            "not_found": not_found,
            "is_accessory": False,
            "skip_sale_stats": False,
            "skip_payments": True,
            "payments_written": True,
        }
