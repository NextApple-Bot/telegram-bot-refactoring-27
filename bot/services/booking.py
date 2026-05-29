# Файл: bot/services/booking.py
import logging
from datetime import datetime

from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class BookingService:
    @staticmethod
    async def process_booking(booking_lines: list, payments: dict = None) -> dict:
        """
        Обрабатывает блок брони: помечает товары как забронированные, сохраняет статистику.
        Принимает опционально уже извлечённые платежи.
        """
        # Локальные импорты для предотвращения циклической зависимости
        from bot.repositories import ItemRepository, StatsRepository
        from bot.services.payment_parser import extract_payment_amounts

        item_lines = []
        for line in booking_lines:
            serials = extract_serials(line)
            if serials:
                item_lines.append(line)

        if not item_lines:
            return {"success": False, "reason": "no_items"}

        if payments is None:
            payments = extract_payment_amounts('\n'.join(booking_lines), ignore_prepay=False)
        total_paid = sum(payments.values())
        amount_per_item = total_paid / len(item_lines) if total_paid else 0

        results = []
        for item_line in item_lines:
            item_info = await ItemRepository.get_item_by_text(item_line)
            if not item_info:
                serials = extract_serials(item_line)
                if serials:
                    item_info = await ItemRepository.get_item_by_serial(serials[0])

            if not item_info:
                results.append({"line": item_line, "status": "not_found"})
                continue

            if 'id' not in item_info:
                logger.error(f"Item info does not contain 'id': {item_info}")
                results.append({"line": item_line, "status": "error", "reason": "no_id"})
                continue

            today = datetime.now().strftime("%d.%m.%y")
            new_text = f"{item_info['text']} (Бронь от {today})"
            await ItemRepository.mark_item_booked(item_info['id'], new_text)

            await StatsRepository.add_booking(item_info['id'], amount_per_item)

            results.append({"line": item_line, "status": "booked", "serial": item_info.get('serial')})

        return {"success": True, "results": results, "payments": payments}
