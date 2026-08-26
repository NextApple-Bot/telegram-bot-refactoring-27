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
)
from web_admin.templates import templates

import logging
logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_SELLERS = ("Тимофей", "Максим")


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


async def _count_sales(session, day):
    from_sales = (await session.execute(
        select(func.count(Sale.id)).where(func.date(Sale.sold_at) == day)
    )).scalar() or 0

    from_payments = (await session.execute(
        select(func.count(DailyPayment.id)).where(
            func.date(DailyPayment.created_at) == day,
            DailyPayment.type == "sale",
        )
    )).scalar() or 0

    return max(from_sales, from_payments)


@router.get("/")
async def dashboard(request: Request, target_date: str | None = None):
    today = datetime.now().date() if not target_date else datetime.strptime(target_date, "%Y-%m-%d").date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            await _ensure_default_sellers(session)

        sales_today = await _count_sales(session, today)
        sales_yesterday = await _count_sales(session, yesterday)
        sales_week_ago = await _count_sales(session, week_ago)

        revenue_today = (await session.execute(
            select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(
                func.date(DailyPayment.created_at) == today)
        )).scalar() or 0

        revenue_yesterday = (await session.execute(
            select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(
                func.date(DailyPayment.created_at) == yesterday)
        )).scalar() or 0

        revenue_week_ago = (await session.execute(
            select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(
                func.date(DailyPayment.created_at) == week_ago)
        )).scalar() or 0

        sales_change_yesterday = calculate_change(sales_today, sales_yesterday)
        sales_change_week = calculate_change(sales_today, sales_week_ago)
        revenue_change_yesterday = calculate_change(float(revenue_today), float(revenue_yesterday))
        revenue_change_week = calculate_change(float(revenue_today), float(revenue_week_ago))

        payment_rows = (await session.execute(
            select(
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "cash"), 0).label("cash"),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "terminal"), 0).label("terminal"),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "qr"), 0).label("qr"),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "transfer"), 0).label("transfer"),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "invoice"), 0).label("invoice"),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "installment"), 0).label("installment"),
            ).where(func.date(DailyPayment.created_at) == today)
        )).one()

        payments = {col: float(getattr(payment_rows, col, 0) or 0) for col in ["cash", "terminal", "qr", "transfer", "invoice", "installment"]}
        total_revenue = sum(payments.values())

        preorders_from_payments = (await session.execute(
            select(func.count(DailyPayment.id)).where(
                func.date(DailyPayment.created_at) == today,
                DailyPayment.type == "preorder",
            )
        )).scalar() or 0

        preorders_from_table = (await session.execute(
            select(func.count(Preorder.id)).where(func.date(Preorder.created_at) == today)
        )).scalar() or 0

        preorders_count = max(preorders_from_payments, preorders_from_table)

        bookings_count = (await session.execute(
            select(func.count(Booking.id)).where(func.date(Booking.booked_at) == today)
        )).scalar() or 0

        active_bookings = (await session.execute(
            select(func.count(Item.id)).where(Item.is_booked.is_(True))
        )).scalar() or 0

        chart_dates, chart_sales, chart_revenue = [], [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            chart_dates.append(d.strftime("%d.%m"))
            chart_sales.append(await _count_sales(session, d))
            rev = (await session.execute(
                select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(
                    func.date(DailyPayment.created_at) == d)
            )).scalar() or 0
            chart_revenue.append(float(rev))

        sellers_rows = (await session.execute(
            select(Seller.id, Seller.name, SellerDay.id.isnot(None).label("present"))
            .outerjoin(SellerDay, (Seller.id == SellerDay.seller_id) & (SellerDay.date == today))
            .order_by(Seller.name)
        )).all()
        sellers = [{"id": r.id, "name": r.name, "present": bool(r.present)} for r in sellers_rows]

        top_models = (await session.execute(
            select(Item.text, func.count(Sale.id).label("count"))
            .select_from(Sale)
            .outerjoin(Item, Item.id == Sale.item_id)
            .where(func.date(Sale.sold_at) >= today - timedelta(days=7))
            .group_by(Item.text)
            .order_by(func.count(Sale.id).desc())
            .limit(5)
        )).all()
        top_labels = [row.text or "—" for row in top_models if row.text]
        top_counts = [row.count for row in top_models if row.text]

    return templates.TemplateResponse("dashboard.html", {
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
            "sales_count": sales_today,
            "preorders_count": preorders_count,
            "bookings_count": bookings_count,
            "active_bookings": active_bookings,
        },
        "sellers": sellers,
        "chart_dates": chart_dates,
        "chart_sales": chart_sales,
        "chart_revenue": chart_revenue,
        "top_labels": top_labels,
        "top_counts": top_counts,
        "days": 7,
    })


@router.post("/toggle_seller_day")
async def toggle_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверная дата"}, status_code=400)

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        existing = (await session.execute(
            select(SellerDay).where(SellerDay.seller_id == seller_id, SellerDay.date == date_obj)
        )).scalar_one_or_none()

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
    Ручное перезаписывание статистики за день.
    Удаляет дневные записи и создаёт новые по введённым суммам/счётчикам.
    """
    try:
        data = await request.json()
    except Exception:
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

    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)

    def _num(key: str) -> float:
        try:
            return float(data.get(key, 0) or 0)
        except (TypeError, ValueError):
            return 0.0

    def _int(key: str) -> int:
        try:
            return max(0, int(float(data.get(key, 0) or 0)))
        except (TypeError, ValueError):
            return 0

    try:
        async_session = get_async_session_factory()
        async with async_session() as session:
            async with session.begin():
                # Удаляем статистику за день через SQLAlchemy (без сырого DATE(:d))
                await session.execute(
                    delete(DailyPayment).where(
                        DailyPayment.created_at >= day_start,
                        DailyPayment.created_at <= day_end,
                    )
                )
                await session.execute(
                    delete(Sale).where(
                        Sale.sold_at >= day_start,
                        Sale.sold_at <= day_end,
                    )
                )
                await session.execute(
                    delete(Preorder).where(
                        Preorder.created_at >= day_start,
                        Preorder.created_at <= day_end,
                    )
                )
                await session.execute(
                    delete(Booking).where(
                        Booking.booked_at >= day_start,
                        Booking.booked_at <= day_end,
                    )
                )

                stamp = day_start

                for pt in ("cash", "terminal", "qr", "transfer", "invoice", "installment"):
                    amount = _num(pt)
                    if amount > 0:
                        session.add(
                            DailyPayment(
                                type="sale",
                                payment_type=pt,
                                amount=amount,
                                created_at=stamp,
                            )
                        )

                sales_count = _int("sales_count")
                for i in range(sales_count):
                    session.add(
                        Sale(
                            item_id=None,
                            count=1,
                            sold_at=stamp,
                            # message_id оставляем NULL — unique допускает несколько NULL
                        )
                    )

                for _ in range(_int("preorders_count")):
                    session.add(Preorder(created_at=stamp))

                for _ in range(_int("bookings_count")):
                    session.add(
                        Booking(
                            item_id=None,
                            total_amount=0,
                            booked_at=stamp,
                        )
                    )

        logger.info("✅ Статистика за %s успешно обновлена", target_date)
        return JSONResponse({"success": True})

    except Exception as e:
        logger.exception("Ошибка update_stats за %s", target_date_str)
        return JSONResponse(
            {"success": False, "error": str(e)[:500]},
            status_code=500,
        )


@router.get("/top_models_data")
async def top_models_data(request: Request, days: int = 7, target_date: str | None = None):
    end_date = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else datetime.now().date()
    start_date = end_date - timedelta(days=days)

    async_session = get_async_session_factory()
    async with async_session() as session:
        top = (await session.execute(
            select(Item.text, func.count(Sale.id).label("count"))
            .select_from(Sale)
            .outerjoin(Item, Item.id == Sale.item_id)
            .where(func.date(Sale.sold_at).between(start_date, end_date))
            .group_by(Item.text)
            .order_by(func.count(Sale.id).desc())
            .limit(5)
        )).all()

    return JSONResponse({
        "labels": [row.text or "—" for row in top],
        "counts": [row.count for row in top],
    })
