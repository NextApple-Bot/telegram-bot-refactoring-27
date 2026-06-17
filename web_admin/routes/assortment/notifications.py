import logging

from aiogram import Bot

from bot import config

logger = logging.getLogger(__name__)


def format_number(value: float | None) -> str:
    if value is None or value == 0:
        return ""
    return f"{int(value):,}".replace(",", " ")


async def send_booking_notification(
    item_text: str,
    serial: str = "",
    price: float | None = None,
    prepayment: float | None = None,
    platform: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
    payment_type: str | None = None,
    birth_date: str | None = None,
    bonus: float | None = None,
    is_cancel: bool = False,
):
    """Уведомление о брони"""
    try:
        bot = Bot(token=config.BOT_TOKEN)

        if is_cancel:
            text = f"❌ Отмена брони:\n\n{item_text}"
        else:
            lines = [f"БРОНЬ:\n{item_text}"]

            if price:
                if bonus:
                    lines.append(f"Стоимость – {format_number(price)} (скидка бонусами {format_number(bonus)})")
                else:
                    lines.append(f"Стоимость – {format_number(price)}")

            if prepayment and prepayment > 0:
                pt_name = {
                    "cash": "наличными",
                    "terminal": "терминалом",
                    "qr": "QR-кодом",
                    "transfer": "переводом",
                }.get(payment_type, payment_type or "")
                lines.append(f"П/О – {format_number(prepayment)} ({pt_name})" if pt_name else f"П/О – {format_number(prepayment)}")

            if full_name: lines.append(full_name)
            if birth_date: lines.append(birth_date)
            if phone: lines.append(phone)
            if platform: lines.append(f"Площадка – {platform}")

            text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=text,
            message_thread_id=config.THREAD_PREORDER,
        )
        await bot.session.close()

    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о брони: {e}")


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
    final_amount: float | None = None,
):
    """Уведомление о продаже с бонусом и сдачей"""
    try:
        bot = Bot(token=config.BOT_TOKEN)
        accessories = accessories or []

        payment_names = {
            "cash": "Наличными",
            "terminal": "Терминал",
            "qr": "QR-код",
            "transfer": "Перевод",
            "invoice": "По счёту",
            "installment": "Рассрочка",
            "paid": "Оплачен",
        }

        lines = [item_text]

        # Стоимость + бонус
        if bonus and bonus > 0:
            lines.append(f"Стоимость – {format_number(price)} (скидка бонусами {format_number(bonus)})")
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

        # Платежи
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

            # Оплата аксессуаров
            for acc in accessories:
                acc_pay = acc.get("payment_type")
                acc_price = acc.get("price", 0)
                if acc_pay and acc_pay != "paid" and acc_price > 0:
                    lines.append(f"{payment_names.get(acc_pay, acc_pay)} – {format_number(acc_price)}")
                    lines.append("")

        # Итоговая сумма
        total = final_amount if final_amount is not None else (price + accessories_total - (bonus or 0))
        if total > 0:
            lines.append(f"Общая сумма – {format_number(total)}")
            lines.append("")

        # Клиент
        if full_name: lines.append(full_name)
        if birth_date: lines.append(birth_date)
        if phone: lines.append(phone)
        lines.append("")

        if platform:
            lines.append(f"Площадка – {platform}")

        text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=text,
            message_thread_id=config.THREAD_SALES,
        )
        await bot.session.close()

        logger.info(f"✅ Уведомление о продаже отправлено: {item_text}")

    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о продаже: {e}")
