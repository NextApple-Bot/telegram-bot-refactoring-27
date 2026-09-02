"""
Сервис обработки бронирования товаров из топика «Предзаказы».

Использует единый контракт finalize_item_booking:
  Item.is_booked + метка текста + Booking + DailyPayment(type=booking).
"""
from __future__ import annotations

import logging
from typing import Any

from bot.db import get_async_session_factory
from bot.services.finalize_booking import finalize_item_booking
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class BookingService:
    """
    Обработка блока бронирования из топика.

    - Поиск товаров по тексту или серийному номеру
    - Финализация через finalize_item_booking (одна транзакция на блок)
    - Платежи блока пишутся один раз (на первый успешно забронированный item)
    """

    @staticmethod
    async def process_booking(
        booking_lines: list[str],
        payments: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        from bot.repositories.item import ItemRepository

        item_lines = [line for line in booking_lines if extract_serials(line)]

        if not item_lines:
            logger.warning("Блок брони не содержит товаров с серийными номерами")
            return {"success": False, "reason": "no_items"}

        if payments is None:
            from bot.services.payment_parser import extract_payment_amounts

            payments = extract_payment_amounts(
                "\n".join(booking_lines), ignore_prepay=False
            )

        total_paid = float(sum(float(v or 0) for v in (payments or {}).values()))
        amount_per_item = total_paid / len(item_lines) if total_paid > 0 else 0.0

        results: list[dict[str, Any]] = []
        processed_count = 0
        failed_count = 0
        payments_written = False

        async_session = get_async_session_factory()
        async with async_session() as session:
            async with session.begin():
                for item_line in item_lines:
                    try:
                        item_info = await ItemRepository.get_item_by_text(
                            item_line, conn=session
                        )
                        if not item_info:
                            serials = extract_serials(item_line)
                            if serials:
                                item_info = await ItemRepository.get_item_by_serial(
                                    serials[0], conn=session
                                )

                        if not item_info:
                            results.append(
                                {
                                    "line": item_line,
                                    "status": "not_found",
                                    "serial": None,
                                }
                            )
                            logger.warning("Товар для брони не найден: %s", item_line)
                            failed_count += 1
                            continue

                        if "id" not in item_info:
                            logger.error("Item info без id: %s", item_info)
                            results.append(
                                {
                                    "line": item_line,
                                    "status": "error",
                                    "reason": "no_id",
                                    "serial": item_info.get("serial"),
                                }
                            )
                            failed_count += 1
                            continue

                        write_pay = (not payments_written) and total_paid > 0
                        meta = await finalize_item_booking(
                            session,
                            item_id=item_info["id"],
                            total_amount=amount_per_item,
                            payments=payments if write_pay else None,
                            write_payments=write_pay,
                            mark_text=True,
                        )
                        if write_pay:
                            payments_written = True

                        results.append(
                            {
                                "line": item_line,
                                "status": "booked",
                                "serial": meta.get("serial") or item_info.get("serial"),
                                "item_id": item_info["id"],
                            }
                        )
                        processed_count += 1
                        logger.info(
                            "✅ Забронирован: id=%s serial=%s amount=%.2f",
                            item_info["id"],
                            item_info.get("serial"),
                            amount_per_item,
                        )
                    except Exception as e:
                        logger.exception("Ошибка бронирования строки: %s", item_line)
                        results.append(
                            {
                                "line": item_line,
                                "status": "error",
                                "reason": str(e),
                                "serial": (
                                    extract_serials(item_line)[0]
                                    if extract_serials(item_line)
                                    else None
                                ),
                            }
                        )
                        failed_count += 1

        success = processed_count > 0
        if success:
            logger.info(
                "Бронирование: ok=%s fail=%s payments_written=%s",
                processed_count,
                failed_count,
                payments_written,
            )
        else:
            logger.warning("Ни один товар из блока брони не обработан")

        return {
            "success": success,
            "results": results,
            "payments": payments,
            "processed_count": processed_count,
            "failed_count": failed_count,
            "payments_written": payments_written,
        }
