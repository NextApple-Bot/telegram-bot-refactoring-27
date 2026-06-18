import logging
from typing import Optional

from aiogram import Bot

from bot import config

logger = logging.getLogger(__name__)


def format_number(value: Optional[float]) -> str:
    """Форматирование числа с пробелами."""
    if value is None or value == 0:
        return "0"
    return f"{int(value):,}".replace(",", " ")


async def send_booking_notification(
    bot: Bot,                           # ← Бот передаётся снаружи
    item_text: str,
    serial: str = "",
    price: Optional[float] = None,
    prepayment: Optional[float] = None,
    platform: Optional[str] = None,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    payment_type: Optional[str] = None,
    birth_date: Optional[str] = None,
    bonus: Optional[float] = None,
    is_cancel: bool = False,
    comment: Optional[str] = None,
):
    """
    Уведомление о брони (максимально близко к формату v26).
    Бот передаётся как аргумент.
    """
    try:
        if is_cancel:
            text = f"❌ Отмена брони:\n\n{item_text}"
        else:
            lines = ["БРОНЬ:", ""]

            if serial:
                lines.append(f"{item_text} ({serial})")
            else:
                lines.append(item_text)

            lines.append("")

            if price:
                if bonus and bonus > 0:
                    lines.append(f"Стоимость – {format_number(price)} (скидка бонусами {format_number(bonus)})")
                else:
                    lines.append(f"Стоимость – {format_number(price)}")
                lines.append("")

            if prepayment and prepayment > 0:
                pt_map = {
                    "cash": "Наличными",
                    "terminal": "Терминалом",
                    "qr": "QR-Кодом",
                    "transfer": "Переводом",
                }
                pt_name = pt_map.get(payment_type, payment_type or "")
                prep_line = f"П/О – {format_number(prepayment)}"
                if pt_name:
                    prep_line += f" ({pt_name})"
                lines.append(prep_line)
                lines.append("")

            if price and prepayment:
                remaining = price - prepayment
                if remaining > 0:
                    lines.append(f"Остаток – {format_number(remaining)}.")
                    lines.append("")
                lines.append(f"Общая – {format_number(price)}.")
                lines.append("")

            if full_name:
                lines.append(full_name)
            if birth_date:
                if not str(birth_date).endswith("г."):
                    birth_date = f"{birth_date}г."
                lines.append(birth_date)
            if phone:
                lines.append(phone)
            if full_name or birth_date or phone:
                lines.append("")

            if platform:
                lines.append(f"Площадка – {platform}.")
                lines.append("")

            if comment:
                lines.append(comment)

            text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=text,
            message_thread_id=config.THREAD_PREORDER,
        )

    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о брони: {e}")


async def send_sale_notification(
    bot: Bot,                           # ← Бот передаётся снаружи
    item_text: str,
    price: float,
    payment_type: str,
    prepayment: Optional[float] = None,
    payment_amount: Optional[float] = None,
    platform: Optional[str] = None,
    full_name: Optional[str] = None,
    phone: Optional[str] = None,
    birth_date: Optional[str] = None,
    bonus: Optional[float] = None,
    change: Optional[float] = None,
    change_type: Optional[str] = None,
    accessories: Optional[list[dict]] = None,
    accessories_total: float = 0.0,
    final_amount: Optional[float] = None,
):
    """
    Уведомление о продаже (максимально близко к формату v26).
    Бот передаётся как аргумент.
    """
    try:
        accessories = accessories or []

        payment_names = {
            "cash": "Наличными",
            "terminal": "Терминалом",
            "qr": "QR-Кодом",
            "transfer": "Переводом",
            "invoice": "По счёту",
            "installment": "Рассрочка",
            "paid": "Оплачен",
        }

        lines = [item_text, ""]

        if bonus and bonus > 0:
            lines.append(f"Стоимость – {format_number(price)} (скидка бонусами {format_number(bonus)})")
        else:
            lines.append(f"Стоимость – {format_number(price)}")
        lines.append("")

        for acc in accessories:
            lines.append(acc.get("text", "Аксессуар"))
            lines.append(f"Стоимость – {format_number(acc.get('price', 0))}")
            lines.append("")

        if prepayment and prepayment > 0:
            lines.append(f"П/О – {format_number(prepayment)}")
            lines.append("")

        if payment_type == "paid":
            lines.append("Оплачен")
            lines.append("")
        else:
            if payment_amount and payment_amount > 0:
                pt_name = payment_names.get(payment_type, payment_type)
                pay_line = f"{pt_name} – {format_number(payment_amount)}"

                if change and change > 0 and change_type == payment_type:
                    pay_line += f" (сдача {'наличными' if change_type == 'cash' else 'переводом'} {format_number(change)})"

                lines.append(pay_line)
                lines.append("")

        total = final_amount if final_amount is not None else (price + accessories_total - (bonus or 0))
        if total > 0:
            lines.append(f"Общая – {format_number(total)}.")
            lines.append("")

        if full_name:
            lines.append(full_name)
        if birth_date:
            if not str(birth_date).endswith("г."):
                birth_date = f"{birth_date}г."
            lines.append(birth_date)
        if phone:
            lines.append(phone)
        if full_name or birth_date or phone:
            lines.append("")

        if platform:
            lines.append(f"Площадка – {platform}.")

        text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=text,
            message_thread_id=config.THREAD_SALES,
        )

        logger.info(f"✅ Уведомление о продаже отправлено: {item_text}")

    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о продаже: {e}")
