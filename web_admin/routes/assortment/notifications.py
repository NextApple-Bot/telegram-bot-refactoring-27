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
    try:
        if is_cancel:
            text = f"❌ Отмена Брони:\n\n{item_text}"
        else:
            lines: list[str] = ["БРОНЬ:", ""]

            serial_clean = (serial or "").strip()
            if serial_clean and f"({serial_clean})" not in item_text:
                lines.append(f"{item_text} ({serial_clean})")
            else:
                lines.append(item_text)

            if price is not None and price > 0:
                if bonus and bonus > 0:
                    lines.append(
                        f"Стоимость – {format_number(price)} "
                        f"(Скидка бонусы {format_number(bonus)})"
                    )
                else:
                    lines.append(f"Стоимость – {format_number(price)}")
                lines.append("")
                lines.append("")

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
                lines.append("")

            if price is not None and price > 0:
                remaining = max(float(price) - prep, 0)
                lines.append(f"Остаток - {format_number(remaining)}")
                lines.append("")
                lines.append(f"Общая – {format_number(price)}.")
                lines.append("")
                lines.append("")

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
                lines.append("")

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
    payments: dict | None = None,
    platform: str | None = None,
    full_name: str | None = None,
    phone: str | None = None,
    birth_date: str | None = None,
    bonus: float | None = None,
    discount: float | None = None,
    change: float | None = None,
    change_type: str | None = None,
    accessories: list[dict] | None = None,
    accessories_total: float = 0.0,
    final_amount: float | None = None,
    comment: str | None = None,
):
    """Уведомление о продаже — формат топика продаж."""
    try:
        accessories = accessories or []
        payments = payments or {}

        payment_names = {
            "cash": "Наличные",
            "terminal": "Терминал",
            "qr": "QR-код",
            "transfer": "Перевод",
            "invoice": "По счёту",
            "installment": "Рассрочка",
            "paid": "Оплачен",
        }

        lines: list[str] = []

        # Товар
        lines.append(item_text if item_text.endswith(".") else f"{item_text}.")

        # Стоимость + скидка/бонусы
        extras = []
        if discount and discount > 0:
            extras.append(f"Скидка {format_number(discount)}")
        if bonus and bonus > 0:
            extras.append(f"бонусы {format_number(bonus)}")
        if extras:
            # как в примере: (Скидка бонусы 3 000) или отдельно
            if discount and bonus:
                note = f"Скидка {format_number(discount)}, бонусы {format_number(bonus)}"
            elif discount:
                note = f"Скидка {format_number(discount)}"
            else:
                note = f"Скидка бонусы {format_number(bonus)}"
            lines.append(f"Стоимость - {format_number(price)} ({note}).")
        else:
            lines.append(f"Стоимость - {format_number(price)}.")
        lines.append("")  # 1 пустая

        # Аксессуары
        for acc in accessories:
            name = (acc.get("text") or acc.get("name") or "Аксессуар").strip()
            if not name.endswith("."):
                name = f"{name}."
            lines.append(name)
            lines.append(f"Стоимость - {format_number(acc.get('price', 0))}.")
            lines.append("")  # 1 пустая после каждого аксессуара

        # ещё одна пустая перед П/О / оплатой (после последнего аксессуара уже есть одна)
        if accessories:
            lines.append("")  # итого 2 пустые перед платежами

        # П/О
        prep = float(prepayment or 0)
        if prep > 0:
            lines.append(f"П/О - {format_number(prep)}.")
            lines.append("")

        # Оплаты по способам
        if payments:
            for pt, amt in payments.items():
                if amt and float(amt) > 0 and pt != "paid":
                    pt_name = payment_names.get(pt, pt)
                    lines.append(f"{pt_name} - {format_number(amt)}.")
                    lines.append("")
        elif payment_type == "paid":
            lines.append("Оплачен.")
            lines.append("")
        elif payment_amount and payment_amount > 0:
            pt_name = payment_names.get(payment_type, payment_type)
            lines.append(f"{pt_name} - {format_number(payment_amount)}.")
            lines.append("")

        # Общая
        total = final_amount if final_amount is not None else (
            float(price) + float(accessories_total or 0)
            - float(bonus or 0) - float(discount or 0)
        )
        if total > 0:
            lines.append(f"Общая - {format_number(total)}.")
            lines.append("")
            lines.append("")  # 2 пустые перед клиентом

        # Клиент
        if full_name:
            lines.append(full_name.strip())
        if phone:
            lines.append(phone.strip())
        if birth_date:
            bd = str(birth_date).strip().replace("г.", "").strip()
            lines.append(bd)
        if full_name or phone or birth_date:
            lines.append("")  # 1 пустая перед площадкой

        if platform:
            lines.append(f"Площадка - {platform.strip()}")

        if comment and comment.strip():
            lines.append("")
            lines.append(comment.strip())

        text = "\n".join(lines)

        await bot.send_message(
            chat_id=config.MAIN_GROUP_ID,
            text=text,
            message_thread_id=config.THREAD_SALES,
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления о продаже: {e}")
