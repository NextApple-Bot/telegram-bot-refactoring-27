from datetime import datetime, timedelta, time

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select

from bot.db import get_async_session_factory
from bot.models import (
    Booking,
    DailyPayment,
    Item,
    Preorder,
    Sale,
    Seller,
    SellerDay,
    StatsAdjustment,
)
from web_admin.templates import templates

import logging
logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_SELLERS = ("Тимофей", "Максим")

PAYMENT_METRICS = ("cash", "terminal", "qr", "transfer", "invoice", "installment")
COUNT_METRICS = ("sales_count", "preorders_count", "bookings_count")
ALL_METRICS = COUNT_METRICS + PAYMENT_METRICS


async def _ensure_default_sellers(session) -> None:
    for name in DEFAULT_SELLERS:
        exists = (
            await session.execute(
                select(Seller.id).where(func.lower(Seller.name) == func.lower(name))
            )
        ).scalar_one_or_none()
        if not exists:
            session.add(Seller(name=name))


def calculate_change(current: int | float, previous: int | float) -> float | None:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


def _parse_number(value) -> float:
    """Числа с точки или запятой (76500,0 → 76500.0)."""
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


async def _load_adjustments(session, day) -> dict[str, float]:
    rows = (
        await session.execute(
            select(StatsAdjustment.metric, StatsAdjustment.delta).where(
                StatsAdjustment.target_date == day
            )
        )
    ).all()
    return {m: float(d or 0) for m, d in rows}


async def _raw_sales_count(session, day) -> int:
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


async def _raw_preorders_count(session, day) -> int:
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


async def _raw_bookings_count(session, day) -> int:
    return int(
        (
            await session.execute(
                select(func.count(Booking.id)).where(func.date(Booking.booked_at) == day)
            )
        ).scalar()
        or 0
    )


async def _raw_payments(session, day) -> dict[str, float]:
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
    return {
        col: float(getattr(payment_rows, col, 0) or 0) for col in PAYMENT_METRICS
    }


async def _day_snapshot(session, day) -> dict:
    """Факт + корректировки за день."""
    adj = await _load_adjustments(session, day)

    raw_sales = await _raw_sales_count(session, day)
    raw_pre = await _raw_preorders_count(session, day)
    raw_book = await _raw_bookings_count(session, day)
    raw_pay = await _raw_payments(session, day)

    sales = max(0, int(round(raw_sales + adj.get("sales_count", 0))))
    preorders = max(0, int(round(raw_pre + adj.get("preorders_count", 0))))
    bookings = max(0, int(round(raw_book + adj.get("bookings_count", 0))))

    payments = {}
    for k in PAYMENT_METRICS:
        payments[k] = max(0.0, float(raw_pay.get(k, 0) + adj.get(k, 0)))

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


@router.get("/")
async def dashboard(request: Request, target_date: str | None = None):
    today = (
        datetime.now().date()
        if not target_date
        else datetime.strptime(target_date, "%Y-%m-%d").date()
    )
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            await _ensure_default_sellers(session)

        snap = await _day_snapshot(session, today)
        snap_y = await _day_snapshot(session, yesterday)
        snap_w = await _day_snapshot(session, week_ago)

        sales_today = snap["sales_count"]
        revenue_today = snap["total_revenue"]

        sales_change_yesterday = calculate_change(sales_today, snap_y["sales_count"])
        sales_change_week = calculate_change(sales_today, snap_w["sales_count"])
        revenue_change_yesterday = calculate_change(
            float(revenue_today), float(snap_y["total_revenue"])
        )
        revenue_change_week = calculate_change(
            float(revenue_today), float(snap_w["total_revenue"])
        )

        payments = snap["payments"]
        total_revenue = snap["total_revenue"]

        active_bookings = (
            await session.execute(
                select(func.count(Item.id)).where(Item.is_booked.is_(True))
            )
        ).scalar() or 0

        chart_dates, chart_sales, chart_revenue = [], [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            s = await _day_snapshot(session, d)
            chart_dates.append(d.strftime("%d.%m"))
            chart_sales.append(s["sales_count"])
            chart_revenue.append(float(s["total_revenue"]))

        sellers_rows = (
            await session.execute(
                select(Seller.id, Seller.name, SellerDay.id.isnot(None).label("present"))
                .outerjoin(
                    SellerDay,
                    (Seller.id == SellerDay.seller_id) & (SellerDay.date == today),
                )
                .order_by(Seller.name)
            )
        ).all()
        sellers = [
            {"id": r.id, "name": r.name, "present": bool(r.present)}
            for r in sellers_rows
        ]

        top_models = (
            await session.execute(
                select(Item.text, func.count(Sale.id).label("count"))
                .select_from(Sale)
                .outerjoin(Item, Item.id == Sale.item_id)
                .where(func.date(Sale.sold_at) >= today - timedelta(days=7))
                .group_by(Item.text)
                .order_by(func.count(Sale.id).desc())
                .limit(5)
            )
        ).all()
        top_labels = [row.text or "—" for row in top_models if row.text]
        top_counts = [row.count for row in top_models if row.text]

        has_adjustments = bool(snap["adjustments"])

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "target_date": today.strftime("%d.%m.%Y"),
            "target_date_iso": today.isoformat(),
            "yesterday_iso": yesterday.isoformat(),
            "sales_today": sales_today,
            "revenue_today": total_revenue,
            "sales_change_yesterday": sales_change_yesterday,
            "sales_change_week": sales_change_week,
            "revenue_change_yesterday": revenue_change_yesterday,
            "revenue_change_week": revenue_change_week,
            "payments": payments,
            "total_revenue": total_revenue,
            "plan_amount": 600000,
            "stats": {
                "sales_count": snap["sales_count"],
                "preorders_count": snap["preorders_count"],
                "bookings_count": snap["bookings_count"],
                "active_bookings": active_bookings,
            },
            "has_adjustments": has_adjustments,
            "sellers": sellers,
            "chart_dates": chart_dates,
            "chart_sales": chart_sales,
            "chart_revenue": chart_revenue,
            "top_labels": top_labels,
            "top_counts": top_counts,
            "days": 7,
        },
    )


@router.post("/toggle_seller_day")
async def toggle_seller_day(
    seller_id: int = Form(...), target_date: str = Form(...)
):
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверная дата"}, status_code=400)

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        existing = (
            await session.execute(
                select(SellerDay).where(
                    SellerDay.seller_id == seller_id, SellerDay.date == date_obj
                )
            )
        ).scalar_one_or_none()

        if existing:
            await session.delete(existing)
            status = "removed"
        else:
            session.add(SellerDay(seller_id=seller_id, date=date_obj))
            status = "added"

    return {"success": True, "status": status}


@router.post("/update_stats")
async def update_stats(request: Request):
    """
    Безопасная правка статистики:
    Sale / DailyPayment / Preorder / Booking НЕ удаляются.
    Пишется корректировка (delta) = target − факт.
    """
    logger.info(
        "📥 update_stats: method=%s path=%s auth=%s",
        request.method,
        request.url.path,
        bool(request.session.get("authenticated")),
    )

    try:
        data = await request.json()
    except Exception as e:
        logger.warning("update_stats: bad JSON: %s", e)
        return JSONResponse(
            {"success": False, "error": "Некорректный JSON"},
            status_code=400,
        )

    target_date_str = data.get("target_date")
    if not target_date_str:
        return JSONResponse(
            {"success": False, "error": "target_date is required"},
            status_code=400,
        )

    try:
        target_date = datetime.strptime(str(target_date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse(
            {"success": False, "error": f"Неверная дата: {target_date_str}"},
            status_code=400,
        )

    reason = (data.get("reason") or "").strip() or None

    def _num(key: str) -> float:
        return _parse_number(data.get(key, 0))

    def _int(key: str) -> int:
        return max(0, int(round(_parse_number(data.get(key, 0)))))

    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            raw_sales = await _raw_sales_count(session, target_date)
            raw_pre = await _raw_preorders_count(session, target_date)
            raw_book = await _raw_bookings_count(session, target_date)
            raw_pay = await _raw_payments(session, target_date)

            targets = {
                "sales_count": float(_int("sales_count")),
                "preorders_count": float(_int("preorders_count")),
                "bookings_count": float(_int("bookings_count")),
            }
            for pt in PAYMENT_METRICS:
                targets[pt] = max(0.0, _num(pt))

            bases = {
                "sales_count": float(raw_sales),
                "preorders_count": float(raw_pre),
                "bookings_count": float(raw_book),
                **{k: float(raw_pay.get(k, 0)) for k in PAYMENT_METRICS},
            }

            # Удаляем старые корректировки за день и пишем актуальный набор
            await session.execute(
                delete(StatsAdjustment).where(
                    StatsAdjustment.target_date == target_date
                )
            )

            written = 0
            for metric in ALL_METRICS:
                base = bases.get(metric, 0.0)
                target = targets.get(metric, 0.0)
                delta = target - base
                # храним и нулевые? только ненулевые — чище
                if abs(delta) < 1e-9:
                    continue
                session.add(
                    StatsAdjustment(
                        target_date=target_date,
                        metric=metric,
                        base_value=base,
                        target_value=target,
                        delta=delta,
                        reason=reason,
                        updated_at=datetime.now(),
                    )
                )
                written += 1

            logger.info(
                "✅ Корректировки за %s: %s метрик (Sale/платежи не трогали)",
                target_date,
                written,
            )

        return JSONResponse(
            {
                "success": True,
                "mode": "adjustment",
                "message": "Сохранено как корректировка. Реальные продажи не удалялись.",
            }
        )

    except Exception as e:
        logger.exception("Ошибка update_stats за %s", target_date_str)
        return JSONResponse(
            {"success": False, "error": str(e)[:500]},
            status_code=500,
        )


@router.get("/top_models_data")
async def top_models_data(
    request: Request, days: int = 7, target_date: str | None = None
):
    end_date = (
        datetime.strptime(target_date, "%Y-%m-%d").date()
        if target_date
        else datetime.now().date()
    )
    start_date = end_date - timedelta(days=days)

    async_session = get_async_session_factory()
    async with async_session() as session:
        top = (
            await session.execute(
                select(Item.text, func.count(Sale.id).label("count"))
                .select_from(Sale)
                .outerjoin(Item, Item.id == Sale.item_id)
                .where(func.date(Sale.sold_at).between(start_date, end_date))
                .group_by(Item.text)
                .order_by(func.count(Sale.id).desc())
                .limit(5)
            )
        ).all()

    return JSONResponse(
        {
            "labels": [row.text or "—" for row in top],
            "counts": [row.count for row in top],
        }
    )
