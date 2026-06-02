import logging

from aiogram import Bot

from bot import config

logger = logging.getLogger(__name__)


def format_number(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:,.0f}".replace(",", " ")


async def send_booking_notification(
    item_text: str,
    serial: str,
    price: float | None = None,
    prepayment: float | None = None,
    platform: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
    payment_type: str | None = None,
    birth_date: str | None = None,
    bonus: float | None = None,
    is_cancel: bool = False,
) -> None:
    """Отправка уведомления о брони (или отмене брони)."""
    try:
        bot = Bot(token=config.BOT_TOKEN)

        if is_cancel:
            message_text = f"❌ Отмена Брони:\n\n{item_text}"
        else:
            lines = ["БРОНЬ:\n", f"{item_text}"]

            if price is not None:
                if bonus:
                    lines.append(f"Стоимость – {format_number(price)} (Скидка бонусы {format_number(bonus)})")
                else:
                    lines.append(f"Стоимость – {format_number(price)}")
            lines.append("")

            if prepayment and prepayment > 0:
                prepayment_str = f"П/О – {format_number(prepayment)}"
                if payment_type:
                    payment_type_ru = {
                        "cash": "Наличными",
                        "terminal": "Терминал",
                        "qr": "QR-код",
                        "transfer": "Перевод",
                        "invoice": "Оплата по счету",
                        "installment": "Рассрочка",
                    }.get(payment_type, payment_type)
                    prepayment_str += f" ({payment_type_ru})"
                lines.append(prepayment_str)
                lines.append("")

            if price is not None:
                total = price - (bonus or 0)
                lines.append(f"Общая – {format_number(total)}")
                lines.append("")

            if full_name:
                lines.append(full_name)
            if birth_date:
                lines.append(birth_date)
            if phone:
                lines.append(phone)
            lines.append("")

            if platform:
                lines.append(f"Площадка – {platform}")

            message_text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=message_text,
            message_thread_id=config.THREAD_PREORDER,
        )
        await bot.session.close()
        logger.info(f"✅ Уведомление о брони отправлено: {item_text}")

    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о брони: {e}")


async def send_sale_notification(
    item_text: str,
    price: float,
    payment_type: str,
    prepayment: float | None = None,
    payment_amount: float | None = None,
    platform: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
    birth_date: str | None = None,
    bonus: float | None = None,
    change: float | None = None,
    change_type: str | None = None,
    accessories: list[dict] | None = None,
    accessories_total: float = 0.0,
) -> None:
    """Отправка детального уведомления о продаже (включая аксессуары)."""
    try:
        bot = Bot(token=config.BOT_TOKEN)

        payment_type_ru = {
            "cash": "Наличными",
            "terminal": "Терминал",
            "qr": "QR-код",
            "transfer": "Перевод",
            "invoice": "Оплата по счету",
            "installment": "Рассрочка",
            "paid": "Оплачен",
        }

        accessories = accessories or []
        lines = [item_text]

        if bonus:
            lines.append(f"Стоимость – {format_number(price)} (Скидка бонусы {format_number(bonus)})")
        else:
            lines.append(f"Стоимость – {format_number(price)}")
        lines.append("")

        # Аксессуары
        if accessories:
            for acc in accessories:
                lines.append(acc.get("text", "Аксессуар"))
                lines.append(f"Стоимость – {format_number(acc.get('price', 0))}")
                lines.append("")
            lines.append("")
        else:
            lines.append("")

        # Платежи
        payments: dict[str, float] = {}
        if payment_type != "paid" and payment_amount and payment_amount > 0:
            payments[payment_type] = payments.get(payment_type, 0) + payment_amount

        if accessories:
            for acc in accessories:
                pay_type = acc.get("payment_type")
                if pay_type and pay_type != "paid" and acc.get("price", 0) > 0:
                    payments[pay_type] = payments.get(pay_type, 0) + acc["price"]

        if prepayment and prepayment > 0:
            lines.append(f"П/О – {format_number(prepayment)}")
            lines.append("")

        if payment_type == "paid":
            lines.append("Оплачен")
            lines.append("")
        else:
            for pt, amount in payments.items():
                if amount > 0:
                    line = f"{payment_type_ru.get(pt, pt)} – {format_number(amount)}"
                    if change and change > 0 and pt == change_type:
                        change_str = f" (сдача {'наличными' if change_type == 'cash' else 'переводом'} - {format_number(change)}₽)"
                        line += change_str
                    lines.append(line)
                    lines.append("")

        # Итоговая сумма
        total = price + accessories_total - (bonus or 0)
        lines.append(f"Общая – {format_number(total)}")
        lines.append("")
        lines.append("")

        if full_name:
            lines.append(full_name)
        if birth_date:
            lines.append(birth_date)
        if phone:
            lines.append(phone)
        lines.append("")

        if platform:
            lines.append(f"Площадка – {platform}")

        message_text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=message_text,
            message_thread_id=config.THREAD_SALES,
        )
        await bot.session.close()
        logger.info(f"✅ Уведомление о продаже отправлено: {item_text}")

    except Exception as e:
        logger.error(f"❌ Ошибка при отправке уведомления о продаже: {e}")
