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
    """
    Формат продажи:

    Товар.
    Стоимость - N.          # без бонусов в скобках; скидка — только если есть
    <1 пустая при аксессуарах / 2 без>
    Аксессуар.
    Стоимость - N.
    <пусто>
    <пусто>
    Наличными - N.
    <пусто>
    UDS - N.                 # если галочка «Бонусы»
    <пусто>
    Общая - N
    <пусто>
    <пусто>
    ФИО / телефон / дата
    <пусто>
    Площадка - ...
    <пусто>
    Комментарий
    """
    try:
        accessories = accessories or []
        payments = dict(payments or {})

        payment_names = {
            "cash": "Наличными",
            "terminal": "Терминал",
            "qr": "QR-код",
            "transfer": "Перевод",
            "invoice": "По счёту",
            "installment": "Рассрочка",
            "paid": "Оплачен",
            "uds": "UDS",
        }

        lines: list[str] = []

        # --- Товар ---
        title = (item_text or "").strip()
        if title and not title.endswith("."):
            title = f"{title}."
        lines.append(title)

        # --- Стоимость: бонусы НЕ пишем в скобках; только скидка ---
        if discount and float(discount) > 0:
            lines.append(
                f"Стоимость - {format_number(price)} (Скидка {format_number(discount)})."
            )
        else:
            lines.append(f"Стоимость - {format_number(price)}.")

        # Отступы + аксессуары
        if accessories:
            lines.append("")  # 1 пустая перед аксессуарами
            for acc in accessories:
                name = (acc.get("text") or acc.get("name") or "Аксессуар").strip()
                if name and not name.endswith("."):
                    name = f"{name}."
                lines.append(name)
                lines.append(f"Стоимость - {format_number(acc.get('price', 0))}.")
                lines.append("")  # 1 пустая после аксессуара
            lines.append("")  # ещё одна → 2 пустые перед оплатами
        else:
            lines.append("")
            lines.append("")

        # --- П/О ---
        prep = float(prepayment or 0)
        if prep > 0:
            lines.append(f"П/О - {format_number(prep)}.")
            lines.append("")

        # --- Оплаты (после каждой — 1 пустая) ---
        # Бонусы → отдельная строка UDS (не в стоимости)
        bonus_val = float(bonus or 0)

        if payments:
            for pt, amt in payments.items():
                if amt and float(amt) > 0 and pt not in ("paid", "uds"):
                    pt_name = payment_names.get(pt, pt)
                    line = f"{pt_name} - {format_number(amt)}."
                    if change and float(change) > 0 and change_type == pt:
                        ch_label = "наличными" if change_type == "cash" else "переводом"
                        line = (
                            f"{pt_name} - {format_number(amt)} "
                            f"(сдача {ch_label} {format_number(change)})."
                        )
                    lines.append(line)
                    lines.append("")
        elif payment_type == "paid":
            lines.append("Оплачен.")
            lines.append("")
        elif payment_amount and float(payment_amount) > 0:
            pt_name = payment_names.get(payment_type, payment_type)
            line = f"{pt_name} - {format_number(payment_amount)}."
            if change and float(change) > 0:
                ch_label = "наличными" if change_type == "cash" else "переводом"
                line = (
                    f"{pt_name} - {format_number(payment_amount)} "
                    f"(сдача {ch_label} {format_number(change)})."
                )
            lines.append(line)
            lines.append("")

        # UDS (бонусы) — как способ оплаты
        if bonus_val > 0:
            lines.append(f"UDS - {format_number(bonus_val)}.")
            lines.append("")

        # --- Общая: цена товара + аксессуары − скидка (бонусы НЕ вычитаем) ---
        total = (
            float(price)
            + float(accessories_total or 0)
            - float(discount or 0)
        )
        if total > 0:
            lines.append(f"Общая - {format_number(total)}")
            lines.append("")
            lines.append("")

        # --- Клиент ---
        if full_name:
            lines.append(full_name.strip())
        if phone:
            lines.append(phone.strip())
        if birth_date:
            bd = str(birth_date).strip().replace("г.", "").strip()
            lines.append(bd)

        if full_name or phone or birth_date:
            lines.append("")

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
