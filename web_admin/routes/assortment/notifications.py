import logging

from aiogram import Bot

from bot import config

logger = logging.getLogger(__name__)


def format_number(value: float | None) -> str:
    if value is None or value == 0:
        return "0"
    return f"{int(value):,}".replace(",", " ")


def _item_title(text: str, serial: str | None = None) -> str:
    title = (text or "").strip()
    serial_clean = (serial or "").strip()
    if serial_clean and f"({serial_clean})" not in title:
        title = f"{title} ({serial_clean})"
    if title and not title.endswith("."):
        title = f"{title}."
    return title


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
    discounts: list[dict] | None = None,
    change: float | None = None,
    change_type: str | None = None,
    accessories: list[dict] | None = None,
    accessories_total: float = 0.0,
    extra_items: list[dict] | None = None,
    final_amount: float | None = None,
    comment: str | None = None,
    trade_in_name: str | None = None,
    trade_in_amount: float | None = None,
    trade_in_serial: str | None = None,
    trade_in_battery: str | None = None,
    gnc_store: str | None = None,
    gnc_amount: float | None = None,
    item_serial: str | None = None,
):
    """
    Trade-in — способ оплаты (не уменьшает Общую).
    Несколько скидок с причинами в строке Стоимость.
    """
    try:
        accessories = accessories or []
        extra_items = extra_items or []
        payments = dict(payments or {})
        discounts = list(discounts or [])
        if not discounts and discount and float(discount) > 0:
            discounts = [{"amount": float(discount), "reason": ""}]

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
        lines.append(_item_title(item_text, item_serial))

        gnc_amt = float(gnc_amount or 0)
        gnc_name = (gnc_store or "").strip()

        cost_extra: list[str] = []
        if gnc_amt > 0:
            if gnc_name:
                cost_extra.append(f"ГНЦ {gnc_name} Скидка - {format_number(gnc_amt)}")
            else:
                cost_extra.append(f"ГНЦ Скидка - {format_number(gnc_amt)}")

        for d in discounts:
            amt = float(d.get("amount") or 0)
            if amt <= 0:
                continue
            reason = (d.get("reason") or "").strip()
            if reason:
                cost_extra.append(f"Скидка {format_number(amt)} {reason}")
            else:
                cost_extra.append(f"Скидка {format_number(amt)}")

        if cost_extra:
            lines.append(
                f"Стоимость - {format_number(price)} ({' + '.join(cost_extra)})."
            )
        else:
            lines.append(f"Стоимость - {format_number(price)}.")
        lines.append("")

        for ex in extra_items:
            ex_text = (ex.get("text") or "").strip()
            ex_serial = (ex.get("serial") or "") or None
            ex_price = float(ex.get("price") or 0)
            lines.append(_item_title(ex_text, ex_serial))
            lines.append(f"Стоимость - {format_number(ex_price)}.")
            lines.append("")

        if accessories:
            for acc in accessories:
                name = (acc.get("text") or acc.get("name") or "Аксессуар").strip()
                if name and not name.endswith("."):
                    name = f"{name}."
                lines.append(name)
                lines.append(f"Стоимость - {format_number(acc.get('price', 0))}.")
                lines.append("")

        trade_amt = float(trade_in_amount or 0)
        if trade_amt > 0:
            tname = (trade_in_name or "Trade-in").strip()
            bat = (trade_in_battery or "").strip()
            tserial = (trade_in_serial or "").strip()
            head = f"Trade IN — {tname}"
            if bat:
                if not bat.endswith("%"):
                    bat = f"{bat}%"
                head += f" ({bat})"
            if tserial:
                head += f" ({tserial})"
            lines.append(head)
            lines.append(f"Стоимость − {format_number(trade_amt)}.")
            lines.append("")

        prep = float(prepayment or 0)
        if prep > 0:
            lines.append(f"П/О - {format_number(prep)}.")
            lines.append("")

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

        if bonus_val > 0:
            lines.append(f"UDS - {format_number(bonus_val)}.")
            lines.append("")

        if final_amount is not None and float(final_amount) >= 0:
            total = float(final_amount)
        else:
            disc_sum = sum(float(d.get("amount") or 0) for d in discounts)
            extra_total = sum(float(ex.get("price") or 0) for ex in extra_items)
            total = (
                float(price)
                + float(accessories_total or 0)
                + float(extra_total)
                - disc_sum
                - float(gnc_amount or 0)
            )
        if total > 0:
            lines.append(f"Общая - {format_number(total)}")
            lines.append("")
            lines.append("")

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
