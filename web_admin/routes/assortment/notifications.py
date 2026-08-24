import logging

from aiogram import Bot

from bot import config

logger = logging.getLogger(__name__)


def format_number(value: float | None) -> str:
    if value is None or value == 0:
        return "0"
    return f"{int(value):,}".replace(",", " ")


async def send_booking_notification(
    bot: Bot,
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
    comment: str | None = None,
    telegram_username: str | None = None,
):
    """Уведомление о брони с точными отступами."""
    try:
        if is_cancel:
            text = f"❌ Отмена Брони:\n\n{item_text}"
        else:
            lines: list[str] = ["БРОНЬ:", ""]

            # Товар (+ serial только если его ещё нет в тексте)
            serial_clean = (serial or "").strip()
            if serial_clean:
                already = (
                    f"({serial_clean})" in item_text
                    or f"[{serial_clean}]" in item_text
                )
                if already:
                    lines.append(item_text)
                else:
                    lines.append(f"{item_text} ({serial_clean})")
            else:
                lines.append(item_text)

            # Стоимость
            if price is not None and price > 0:
                if bonus and bonus > 0:
                    lines.append(
                        f"Стоимость – {format_number(price)} "
                        f"(Скидка бонусы {format_number(bonus)})"
                    )
                else:
                    lines.append(f"Стоимость – {format_number(price)}")
                # два пустых после стоимости
                lines.append("")
                lines.append("")

            # Предоплата
            prep = float(prepayment or 0)
            if prep > 0:
                pt_map = {
                    "cash": "Наличными",
                    "terminal": "Терминалом",
                    "qr": "QR-Кодом",
                    "transfer": "Переводом",
                }
                pt_name = pt_map.get(payment_type or "", payment_type or "")
                prep_line = f"П/О – {format_number(prep)}"
                if pt_name:
                    prep_line += f" ({pt_name})"
                lines.append(prep_line)
                lines.append("")  # один пустой

            # Остаток + Общая
            if price is not None and price > 0:
                remaining = float(price) - prep
                if remaining < 0:
                    remaining = 0
                lines.append(f"Остаток - {format_number(remaining)}")
                lines.append("")  # один пустой
                lines.append(f"Общая – {format_number(price)}.")
                # два пустых перед клиентом
                lines.append("")
                lines.append("")

            # Клиент: ФИО → телефон → дата рождения
            if full_name:
                lines.append(full_name.strip())
            if phone:
                lines.append(phone.strip())
            if birth_date:
                bd = str(birth_date).strip()
                if bd and not bd.endswith("г."):
                    bd = f"{bd}г."
                lines.append(bd)

            if telegram_username:
                uname = telegram_username.strip()
                if uname and not uname.startswith("@"):
                    uname = f"@{uname}"
                lines.append(f"ТГ – {uname}")

            if full_name or birth_date or phone or telegram_username:
                lines.append("")  # один пустой перед площадкой

            if platform:
                lines.append(f"Площадка – {platform.strip()}.")

            if comment and comment.strip():
                if platform:
                    lines.append("")
                lines.append(comment.strip())

            text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=text,
            message_thread_id=config.THREAD_PREORDER,
        )

    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о брони: {e}")


async def send_sale_notification(
    bot: Bot,
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
    """Уведомление о продаже."""
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
            lines.append(
                f"Стоимость – {format_number(price)} "
                f"(Скидка бонусы {format_number(bonus)})"
            )
        else:
            lines.append(f"Стоимость – {format_number(price)}")
        lines.append("")

        for acc in accessories:
            lines.append(acc.get("text", "Аксессуар"))
            lines.append(f"Стоимость – {format_number(acc.get('price', 0))}")
            lines.append("")

        prep = float(prepayment or 0)
        if prep > 0:
            lines.append(f"П/О – {format_number(prep)}")
            lines.append("")

        if prep > 0 and price:
            remaining = float(price) - prep
            if remaining < 0:
                remaining = 0
            lines.append(f"Остаток - {format_number(remaining)}")
            lines.append("")

        if payment_type == "paid":
            lines.append("Оплачен")
            lines.append("")
        else:
            if payment_amount and payment_amount > 0:
                pt_name = payment_names.get(payment_type, payment_type)
                pay_line = f"{pt_name} – {format_number(payment_amount)}"

                if change and change > 0 and change_type == payment_type:
                    pay_line += (
                        f" (сдача {'наличными' if change_type == 'cash' else 'переводом'} "
                        f"{format_number(change)})"
                    )

                lines.append(pay_line)
                lines.append("")

        total = final_amount if final_amount is not None else (
            price + accessories_total - (bonus or 0)
        )
        if total > 0:
            lines.append(f"Общая – {format_number(total)}.")
            lines.append("")

        if full_name:
            lines.append(full_name)
        if phone:
            lines.append(phone)
        if birth_date:
            bd = str(birth_date).strip()
            if bd and not bd.endswith("г."):
                bd = f"{bd}г."
            lines.append(bd)
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

    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о продаже: {e}")
