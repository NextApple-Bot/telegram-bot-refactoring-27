"""
Единый снимок дня: raw-данные + StatsAdjustment.

Используется дашбордом, статистикой продавцов и (по возможности) stats.
Не дублировать эту логику в роутах.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy import delete, func, select

from bot.models import Booking, DailyPayment, Preorder, Sale, StatsAdjustment

logger = logging.getLogger(__name__)

PAYMENT_METRICS = ("cash", "terminal", "qr", "transfer", "invoice", "installment")
COUNT_METRICS = ("sales_count", "preorders_count", "bookings_count")
ALL_METRICS = COUNT_METRICS + PAYMENT_METRICS


async def load_adjustments(session, day: date) -> dict[str, float]:
    rows = (
        await session.execute(
            select(StatsAdjustment.metric, StatsAdjustment.delta).where(
                StatsAdjustment.target_date == day
            )
        )
    ).all()
    return {m: float(d or 0) for m, d in rows}


async def load_adjustments_range(
    session, start_date: date, end_date: date
) -> dict:
    """
    by_day[date][metric] = delta
    totals[metric] = sum(delta)
    """
    rows = (
        await session.execute(
            select(
                StatsAdjustment.target_date,
                StatsAdjustment.metric,
                StatsAdjustment.delta,
            ).where(StatsAdjustment.target_date.between(start_date, end_date))
        )
    ).all()

    by_day: dict[date, dict[str, float]] = {}
    totals: dict[str, float] = {}
    for d, metric, delta in rows:
        day = d if isinstance(d, date) else d
        val = float(delta or 0)
        if day not in by_day:
            by_day[day] = {}
        by_day[day][metric] = by_day[day].get(metric, 0.0) + val
        totals[metric] = totals.get(metric, 0.0) + val
    return {"by_day": by_day, "totals": totals}


async def raw_sales_count(session, day: date) -> int:
    from_sales = (
        await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == day)
        )
    ).scalar() or 0
    from_payments = (
        await session.execute(
            select(func.count(DailyPayment.id)).where(
                func.date(DailyPayment.created_at) == day,
                DailyPayment.type == "sale",
            )
        )
    ).scalar() or 0
    return int(max(from_sales, from_payments))


async def raw_preorders_count(session, day: date) -> int:
    from_payments = (
        await session.execute(
            select(func.count(DailyPayment.id)).where(
                func.date(DailyPayment.created_at) == day,
                DailyPayment.type == "preorder",
            )
        )
    ).scalar() or 0
    from_table = (
        await session.execute(
            select(func.count(Preorder.id)).where(func.date(Preorder.created_at) == day)
        )
    ).scalar() or 0
    return int(max(from_payments, from_table))


async def raw_bookings_count(session, day: date) -> int:
    return int(
        (
            await session.execute(
                select(func.count(Booking.id)).where(func.date(Booking.booked_at) == day)
            )
        ).scalar()
        or 0
    )


async def raw_payments(session, day: date) -> dict[str, float]:
    payment_rows = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "cash"
                    ),
                    0,
                ).label("cash"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "terminal"
                    ),
                    0,
                ).label("terminal"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "qr"
                    ),
                    0,
                ).label("qr"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "transfer"
                    ),
                    0,
                ).label("transfer"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "invoice"
                    ),
                    0,
                ).label("invoice"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "installment"
                    ),
                    0,
                ).label("installment"),
            ).where(func.date(DailyPayment.created_at) == day)
        )
    ).one()
    return {col: float(getattr(payment_rows, col, 0) or 0) for col in PAYMENT_METRICS}


async def day_snapshot(session, day: date) -> dict:
    """
    Итоговые KPI за день = raw + StatsAdjustment.

    Возвращает:
      sales_count, preorders_count, bookings_count,
      payments{...}, total_revenue,
      raw{...}, adjustments{...}
    """
    adj = await load_adjustments(session, day)

    raw_sales = await raw_sales_count(session, day)
    raw_pre = await raw_preorders_count(session, day)
    raw_book = await raw_bookings_count(session, day)
    raw_pay = await raw_payments(session, day)

    sales = max(0, int(round(raw_sales + adj.get("sales_count", 0))))
    preorders = max(0, int(round(raw_pre + adj.get("preorders_count", 0))))
    bookings = max(0, int(round(raw_book + adj.get("bookings_count", 0))))

    payments = {
        k: max(0.0, float(raw_pay.get(k, 0) + adj.get(k, 0))) for k in PAYMENT_METRICS
    }

    return {
        "sales_count": sales,
        "preorders_count": preorders,
        "bookings_count": bookings,
        "payments": payments,
        "total_revenue": sum(payments.values()),
        "raw": {
            "sales_count": raw_sales,
            "preorders_count": raw_pre,
            "bookings_count": raw_book,
            "payments": raw_pay,
        },
        "adjustments": adj,
    }


async def month_totals(session, day: date) -> dict:
    """Сумма скорректированных KPI за календарный месяц выбранного дня."""
    first = day.replace(day=1)
    last_day = calendar.monthrange(day.year, day.month)[1]
    last = day.replace(day=last_day)

    sales = 0
    revenue = 0.0
    preorders = 0
    bookings = 0
    payments = {k: 0.0 for k in PAYMENT_METRICS}
    days_with_data = 0

    d = first
    while d <= last:
        s = await day_snapshot(session, d)
        sales += s["sales_count"]
        preorders += s["preorders_count"]
        bookings += s["bookings_count"]
        revenue += float(s["total_revenue"])
        for k in PAYMENT_METRICS:
            payments[k] += float(s["payments"].get(k, 0))
        if (
            s["sales_count"]
            or s["preorders_count"]
            or s["bookings_count"]
            or s["total_revenue"]
            or s["adjustments"]
        ):
            days_with_data += 1
        d += timedelta(days=1)

    return {
        "sales_count": sales,
        "preorders_count": preorders,
        "bookings_count": bookings,
        "revenue": revenue,
        "payments": payments,
        "days_with_data": days_with_data,
        "month_label": first.strftime("%m.%Y"),
        "month_name": first.strftime("%B %Y"),
        "first": first.isoformat(),
        "last": last.isoformat(),
    }


async def clear_adjustments_for_dates(session, days: Iterable[date]) -> int:
    """
    Удаляет StatsAdjustment за указанные дни.
    Вызывать после отмены продаж, чтобы цифры снова отражали raw.
    Возвращает число затронутых дней (уникальных).
    """
    unique = sorted({d for d in days if d is not None})
    if not unique:
        return 0
    result = await session.execute(
        delete(StatsAdjustment).where(StatsAdjustment.target_date.in_(unique))
    )
    deleted = result.rowcount if result.rowcount is not None else 0
    logger.info(
        "Сброшены StatsAdjustment за дни %s (rows≈%s)",
        [d.isoformat() for d in unique],
        deleted,
    )
    return len(unique)


def as_date(value) -> date | None:
    """Достаёт date из datetime / date / None."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
