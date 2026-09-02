"""
Единый снимок дня: raw-данные + StatsAdjustment.

Используется дашбордом, статистикой продавцов и (по возможности) stats.
Не дублировать эту логику в роутах.
"""
from __future__ import annotations

import calendar
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Iterable
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select

from bot.models import Booking, DailyPayment, Preorder, Sale, StatsAdjustment

logger = logging.getLogger(__name__)

PAYMENT_METRICS = ("cash", "terminal", "qr", "transfer", "invoice", "installment")
COUNT_METRICS = ("sales_count", "preorders_count", "bookings_count")
ALL_METRICS = COUNT_METRICS + PAYMENT_METRICS

METRIC_LABELS = {
    "sales_count": "Продажи, шт.",
    "preorders_count": "Предзаказы, шт.",
    "bookings_count": "Брони, шт.",
    "cash": "Наличные, ₽",
    "terminal": "Терминал, ₽",
    "qr": "QR-код, ₽",
    "transfer": "Перевод, ₽",
    "invoice": "По счёту, ₽",
    "installment": "Рассрочка, ₽",
    "total_revenue": "Выручка (Σ оплат), ₽",
}

APP_TZ_NAME = os.getenv("APP_TZ", "Europe/Moscow")
try:
    APP_TZ = ZoneInfo(APP_TZ_NAME)
except Exception:
    APP_TZ = timezone(timedelta(hours=3))
    logger.warning("Не удалось загрузить ZoneInfo(%s), используем UTC+3", APP_TZ_NAME)


def now_local() -> datetime:
    return datetime.now(APP_TZ)


def today_local() -> date:
    return now_local().date()


def as_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.date()
        return value.astimezone(APP_TZ).date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


async def load_adjustments(session, day: date) -> dict[str, float]:
    rows = (
        await session.execute(
            select(StatsAdjustment.metric, StatsAdjustment.delta).where(
                StatsAdjustment.target_date == day
            )
        )
    ).all()
    return {m: float(d or 0) for m, d in rows}


async def load_adjustments_detail(session, day: date) -> list[dict]:
    rows = (
        await session.execute(
            select(StatsAdjustment)
            .where(StatsAdjustment.target_date == day)
            .order_by(StatsAdjustment.metric)
        )
    ).scalars().all()
    out = []
    for r in rows:
        out.append(
            {
                "metric": r.metric,
                "base_value": float(r.base_value or 0),
                "target_value": float(r.target_value or 0),
                "delta": float(r.delta or 0),
                "reason": r.reason or "",
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
        )
    return out


async def load_adjustments_range(session, start_date: date, end_date: date) -> dict:
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


def build_day_reconciliation(snap: dict) -> dict:
    """
    Сверка дня: факт из БД / корректировка / итог на дашборде.

    snap — результат day_snapshot().
    """
    rows: list[dict] = []
    has_adj = False

    for key in COUNT_METRICS:
        raw = float(snap.get("raw", {}).get(key, 0) or 0)
        delta = float(snap.get("adjustments", {}).get(key, 0) or 0)
        final = float(snap.get(key, 0) or 0)
        if abs(delta) > 1e-9:
            has_adj = True
        rows.append(
            {
                "key": key,
                "label": METRIC_LABELS.get(key, key),
                "kind": "count",
                "raw": raw,
                "delta": delta,
                "final": final,
                "changed": abs(delta) > 1e-9,
            }
        )

    raw_pay = snap.get("raw", {}).get("payments") or {}
    fin_pay = snap.get("payments") or {}
    adj = snap.get("adjustments") or {}
    for key in PAYMENT_METRICS:
        raw = float(raw_pay.get(key, 0) or 0)
        delta = float(adj.get(key, 0) or 0)
        final = float(fin_pay.get(key, 0) or 0)
        if abs(delta) > 1e-9:
            has_adj = True
        rows.append(
            {
                "key": key,
                "label": METRIC_LABELS.get(key, key),
                "kind": "money",
                "raw": raw,
                "delta": delta,
                "final": final,
                "changed": abs(delta) > 1e-9,
            }
        )

    raw_total = float(sum(float(raw_pay.get(k, 0) or 0) for k in PAYMENT_METRICS))
    final_total = float(snap.get("total_revenue", 0) or 0)
    delta_total = final_total - raw_total
    if abs(delta_total) > 0.01:
        has_adj = True

    rows.append(
        {
            "key": "total_revenue",
            "label": METRIC_LABELS["total_revenue"],
            "kind": "money",
            "raw": raw_total,
            "delta": delta_total,
            "final": final_total,
            "changed": abs(delta_total) > 0.01,
            "is_total": True,
        }
    )

    return {
        "rows": rows,
        "has_adjustments": has_adj,
        "raw_total": raw_total,
        "final_total": final_total,
        "delta_total": delta_total,
        "changed_count": sum(1 for r in rows if r.get("changed")),
    }


async def month_totals(session, day: date) -> dict:
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
