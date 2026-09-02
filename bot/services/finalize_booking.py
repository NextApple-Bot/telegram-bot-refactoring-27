"""
Единая финализация брони в БД.

Используется:
  - топик Предзаказы (BookingService)
  - админка (web_admin/routes/assortment/booking.py)

Гарантирует в рамках уже открытой сессии/транзакции:
  1) Item.is_booked = True (+ опционально текст «Бронь от DD.MM.YY» и поля клиента)
  2) запись Booking (если товар ещё не был в брони)
  3) DailyPayment type='booking' (если write_payments и есть суммы)

Платежи пишутся один раз на блок (write_payments=True только у первого item
при мульти-SN), по аналогии с finalize_item_sale.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Booking, DailyPayment, Item
from bot.services.finalize_sale import PAYMENT_TYPES, normalize_payments

logger = logging.getLogger(__name__)

_BOOKING_MARK_RE = re.compile(r"\s*\(Бронь от [^)]+\)\s*", re.IGNORECASE)


def _booking_mark_text(current_text: str, when: datetime | None = None) -> str:
    """Добавляет/обновляет метку «(Бронь от DD.MM.YY)» без дублей."""
    base = _BOOKING_MARK_RE.sub(" ", current_text or "").strip()
    base = re.sub(r"\s+", " ", base).strip(" ,.;")
    day = (when or datetime.now()).strftime("%d.%m.%y")
    return f"{base} (Бронь от {day})" if base else f"(Бронь от {day})"


async def finalize_item_booking(
    session: AsyncSession,
    *,
    item_id: int,
    total_amount: float = 0.0,
    payments: dict[str, float] | None = None,
    write_payments: bool = True,
    mark_text: bool = True,
    # поля с формы админки (опционально)
    booking_price: float | None = None,
    booking_prepayment: float | None = None,
    booking_payment_type: str | None = None,
    booking_platform: str | None = None,
    booking_full_name: str | None = None,
    booking_phone: str | None = None,
    booking_birth_date: str | None = None,
    booking_bonus: float | None = None,
) -> dict[str, Any]:
    """
    Бронирует один товар внутри уже открытой транзакции.

    Returns:
        item_id, was_booked, payments, text
    """
    item = await session.get(Item, item_id)
    if item is None:
        raise ValueError(f"item_not_found:{item_id}")

    was_booked = bool(item.is_booked)
    pays = normalize_payments(payments if write_payments else None)

    item.is_booked = True

    if mark_text:
        item.text = _booking_mark_text(item.text or "")

    if booking_price is not None:
        item.booking_price = booking_price
    if booking_prepayment is not None:
        item.booking_prepayment = booking_prepayment
    if booking_payment_type is not None:
        item.booking_payment_type = booking_payment_type
    if booking_platform is not None:
        item.booking_platform = booking_platform
    if booking_full_name is not None:
        item.booking_full_name = booking_full_name
    if booking_phone is not None:
        item.booking_phone = booking_phone
    if booking_birth_date is not None:
        item.booking_birth_date = booking_birth_date
    if booking_bonus is not None:
        item.booking_bonus = booking_bonus

    amount = float(total_amount or 0)
    if amount <= 0 and booking_price is not None:
        amount = float(booking_price or 0)
    if amount <= 0 and write_payments:
        amount = float(sum(pays.values()))

    # Booking-счётчик только при первой брони
    if not was_booked:
        session.add(
            Booking(
                item_id=item.id,
                total_amount=amount if amount > 0 else None,
            )
        )

    if write_payments:
        for pt, val in pays.items():
            if val and float(val) > 0:
                session.add(
                    DailyPayment(
                        type="booking",
                        payment_type=pt,
                        amount=float(val),
                    )
                )

    await session.flush()

    logger.info(
        "finalize_item_booking: item_id=%s was_booked=%s amount=%s payments=%s",
        item_id,
        was_booked,
        amount,
        pays if write_payments else "(deferred)",
    )

    return {
        "item_id": item_id,
        "was_booked": was_booked,
        "text": item.text,
        "serial": item.serial,
        "payments": pays,
        "amount": amount,
    }
