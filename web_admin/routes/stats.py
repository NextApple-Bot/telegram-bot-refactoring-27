from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import Booking, DailyPayment, Preorder, Sale
from bot.repositories.stats import StatsRepository
from web_admin.templates import templates

router = APIRouter()


@router.get("/")
async def stats_page(
    request: Request,
    target_date: str | None = None,
    days: int = Query(7, ge=1, le=365),
    mode: str = Query("preset"),
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    if not target_date:
        target_date = date.today().isoformat()

    target = datetime.strptime(target_date, "%Y-%m-%d").date()

    # Определяем период
    if mode == "preset":
        start_date = target - timedelta(days=days - 1)
        end_date = target
    elif mode == "month" and month:
        year, mon = map(int, month.split("-"))
        start_date = date(year, mon, 1)
        if mon == 12:
            end_date = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            end_date = date(year, mon + 1, 1) - timedelta(days=1)
    elif date_from and date_to:
        start_date = datetime.strptime(date_from, "%Y-%m-%d").date()
        end_date = datetime.strptime(date_to, "%Y-%m-%d").date()
    else:
        start_date = target - timedelta(days=6)
        end_date = target

    async_session = get_async_session_factory()
    async with async_session() as session:
        # Получаем агрегированную статистику за период
        sales_data = await session.execute(
            select(
                func.coalesce(func.sum(Sale.cash), 0).label("cash"),
                func.coalesce(func.sum(Sale.terminal), 0).label("terminal"),
                func.coalesce(func.sum(Sale.qr), 0).label("qr"),
                func.coalesce(func.sum(Sale.transfer), 0).label("transfer"),
                func.coalesce(func.sum(Sale.invoice), 0).label("invoice"),
                func.coalesce(func.sum(Sale.installment), 0).label("installment"),
                func.count(Sale.id).label("count"),
            ).where(func.date(Sale.sold_at).between(start_date, end_date))
        )
        sales_row = sales_data.mappings().one()

        preorders_data = await session.execute(
            select(
                func.coalesce(func.sum(Preorder.cash), 0).label("cash"),
                func.coalesce(func.sum(Preorder.terminal), 0).label("terminal"),
                func.coalesce(func.sum(Preorder.qr), 0).label("qr"),
                func.coalesce(func.sum(Preorder.transfer), 0).label("transfer"),
                func.coalesce(func.sum(Preorder.invoice), 0).label("invoice"),
                func.coalesce(func.sum(Preorder.installment), 0).label("installment"),
                func.count(Preorder.id).label("count"),
            ).where(func.date(Preorder.created_at).between(start_date, end_date))
        )
        preorders_row = preorders_data.mappings().one()

        bookings_data = await session.execute(
            select(
                func.coalesce(func.sum(Booking.total_amount), 0).label("total"),
                func.count(Booking.id).label("count"),
            ).where(func.date(Booking.booked_at).between(start_date, end_date))
        )
        bookings_row = bookings_data.mappings().one()

        # График по дням
        chart_dates = []
        chart_sales = []
        chart_revenue = []

        current = start_date
        while current <= end_date:
            chart_dates.append(current.strftime("%d.%m"))

            day_sales = (await session.execute(
                select(func.count(Sale.id)).where(func.date(Sale.sold_at) == current)
            )).scalar() or 0

            day_revenue = (await session.execute(
                select(func.coalesce(func.sum(DailyPayment.amount), 0))
                .where(func.date(DailyPayment.created_at) == current)
            )).scalar() or 0

            chart_sales.append(day_sales)
            chart_revenue.append(float(day_revenue))
            current += timedelta(days=1)

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "mode": mode,
            "target_date": target_date,
            "days": days,
            "month": month,
            "date_from": date_from,
            "date_to": date_to,
            "sales_count": sales_row["count"],
            "preorders_count": preorders_row["count"],
            "bookings_count": bookings_row["count"],
            "payment_labels": ["Наличные", "Терминал", "QR", "Перевод", "По счёту", "Рассрочка"],
            "payment_values": [
                float(sales_row["cash"]),
                float(sales_row["terminal"]),
                float(sales_row["qr"]),
                float(sales_row["transfer"]),
                float(sales_row["invoice"]),
                float(sales_row["installment"]),
            ],
            "chart_dates": chart_dates,
            "chart_revenue": chart_revenue,
            "chart_sales": chart_sales,
        },
    )
