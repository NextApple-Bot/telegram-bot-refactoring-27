import logging
from datetime import datetime
from typing import Any

from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class BookingService:
    """
    Сервис обработки бронирования товаров из топика «Предзаказы».

    Отвечает за:
    - Поиск товаров по тексту или серийному номеру
    - Пометку товаров как забронированных
    - Сохранение статистики брони
    - Возврат детального отчёта по каждому товару
    """

    @staticmethod
    async def process_booking(
        booking_lines: list[str],
        payments: dict[str, float] | None = None
    ) -> dict[str, Any]:
        """
        Обрабатывает блок бронирования.

        Args:
            booking_lines: Список строк из сообщения (включая строки с оплатой)
            payments: Уже извлечённые суммы платежей (опционально).
                      Если не переданы — извлекаются автоматически.

        Returns:
            dict с ключами:
                - success: True/False
                - reason: причина неудачи (например "no_items")
                - results: список результатов по каждому товару
                - payments: использованные суммы платежей
        """
        # Локальные импорты для предотвращения циклических зависимостей
        from bot.repositories.item import ItemRepository
        from bot.repositories.stats import StatsRepository

        # Фильтруем только строки, содержащие серийные номера
        item_lines = [line for line in booking_lines if extract_serials(line)]

        if not item_lines:
            logger.warning("Блок брони не содержит товаров с серийными номерами")
            return {"success": False, "reason": "no_items"}

        # Если платежи не переданы — извлекаем из всех строк блока
        if payments is None:
            from bot.services.payment_parser import extract_payment_amounts
            payments = extract_payment_amounts('\n'.join(booking_lines), ignore_prepay=False)

        total_paid = sum(payments.values())
        amount_per_item = total_paid / len(item_lines) if total_paid > 0 else 0.0

        results: list[dict[str, Any]] = []
        processed_count = 0
        failed_count = 0

        for item_line in item_lines:
            try:
                # Сначала пытаемся найти по полному тексту строки
                item_info = await ItemRepository.get_item_by_text(item_line)

                # Если не нашли по тексту — ищем по первому серийному номеру
                if not item_info:
                    serials = extract_serials(item_line)
                    if serials:
                        item_info = await ItemRepository.get_item_by_serial(serials[0])

                if not item_info:
                    results.append({
                        "line": item_line,
                        "status": "not_found",
                        "serial": None
                    })
                    logger.warning(f"Товар для брони не найден: {item_line}")
                    failed_count += 1
                    continue

                # Проверка наличия id (защита от некорректных данных из репозитория)
                if "id" not in item_info:
                    logger.error(f"Item info не содержит 'id': {item_info}")
                    results.append({
                        "line": item_line,
                        "status": "error",
                        "reason": "no_id",
                        "serial": item_info.get("serial")
                    })
                    failed_count += 1
                    continue

                # Формируем новый текст с отметкой о брони
                today = datetime.now().strftime("%d.%m.%y")
                new_text = f"{item_info['text']} (Бронь от {today})"

                # Помечаем товар как забронированный
                await ItemRepository.mark_item_booked(item_info["id"], new_text)

                # Сохраняем статистику брони
                await StatsRepository.add_booking(
                    item_id=item_info["id"],
                    total_amount=amount_per_item
                )

                results.append({
                    "line": item_line,
                    "status": "booked",
                    "serial": item_info.get("serial"),
                    "item_id": item_info["id"]
                })

                processed_count += 1
                logger.info(
                    f"✅ Забронирован товар: id={item_info['id']}, "
                    f"serial={item_info.get('serial')}, amount={amount_per_item:.2f}"
                )

            except Exception as e:
                logger.exception(f"Ошибка при бронировании строки: {item_line}")
                results.append({
                    "line": item_line,
                    "status": "error",
                    "reason": str(e),
                    "serial": extract_serials(item_line)[0] if extract_serials(item_line) else None
                })
                failed_count += 1

        success = processed_count > 0

        if success:
            logger.info(
                f"Бронирование завершено: успешно={processed_count}, "
                f"ошибок/не найдено={failed_count}"
            )
        else:
            logger.warning("Ни один товар из блока брони не был успешно обработан")

        return {
            "success": success,
            "results": results,
            "payments": payments,
            "processed_count": processed_count,
            "failed_count": failed_count
        }
