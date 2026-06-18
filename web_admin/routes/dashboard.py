from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from bot.db import get_async_session_factory
from bot.models import (
    Booking,
    Category,
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


def calculate_change(current: int | float, previous: int | float) -> float | None:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


@router.get("/")
async def dashboard(request: Request, target_date: str | None = None):
    today = datetime.now().date() if not target_date else datetime.strptime(target_date, "%Y-%m-%d").date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)
    yesterday_iso = yesterday.isoformat()

    async_session = get_async_session_factory()
    async with async_session() as session:
        # KPI
        sales_today = (await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == today)
        )).scalar() or 0

        sales_yesterday = (await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == yesterday)
        )).scalar() or 0

        sales_week_ago = (await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == week_ago)
        )).scalar() or 0

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
        revenue_change_yesterday = calculate_change(revenue_today, revenue_yesterday)
        revenue_change_week = calculate_change(revenue_today, revenue_week_ago)

        # Платежи
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

        payments = {col: getattr(payment_rows, col, 0) for col in ["cash", "terminal", "qr", "transfer", "invoice", "installment"]}
        total_revenue = sum(payments.values())

        # Предзаказы и брони
        preorders_count = (await session.execute(
            select(func.count(Preorder.id)).where(func.date(Preorder.created_at) == today)
        )).scalar() or 0

        bookings_count = (await session.execute(
            select(func.count(Booking.id)).where(func.date(Booking.booked_at) == today)
        )).scalar() or 0

        # Графики
        chart_dates, chart_sales, chart_revenue = [], [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            chart_dates.append(d.strftime("%d.%m"))
            sales_cnt = (await session.execute(
                select(func.count(Sale.id)).where(func.date(Sale.sold_at) == d)
            )).scalar() or 0
            rev = (await session.execute(
                select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(
                    func.date(DailyPayment.created_at) == d)
            )).scalar() or 0
            chart_sales.append(sales_cnt)
            chart_revenue.append(float(rev))

        # Продавцы
        sellers_rows = (await session.execute(
            select(Seller.id, Seller.name, SellerDay.id.isnot(None).label("present"))
            .outerjoin(SellerDay, (Seller.id == SellerDay.seller_id) & (SellerDay.date == today))
            .order_by(Seller.name)
        )).all()
        sellers = [{"id": r.id, "name": r.name, "present": bool(r.present)} for r in sellers_rows]

        # Топ моделей
        top_models = (await session.execute(
            select(Item.text, func.count(Sale.id).label("count"))
            .join(Sale, Sale.item_id == Item.id)
            .where(func.date(Sale.sold_at) >= today - timedelta(days=7))
            .group_by(Item.text)
            .order_by(func.count(Sale.id).desc())
            .limit(5)
        )).all()
        top_labels = [row.text for row in top_models]
        top_counts = [row.count for row in top_models]

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
    data = await request.json()
    target_date_str = data.get("target_date")

    if not target_date_str:
        return JSONResponse({"success": False, "error": "target_date is required"}, status_code=400)

    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    async_session = get_async_session_factory()

    async with async_session() as session:
        async with session.begin():
            # Очистка
            await session.execute(text("DELETE FROM daily_payments WHERE DATE(created_at) = :d"), {"d": target_date})
            await session.execute(text("DELETE FROM sales WHERE DATE(sold_at) = :d"), {"d": target_date})
            await session.execute(text("DELETE FROM preorders WHERE DATE(created_at) = :d"), {"d": target_date})
            await session.execute(text("DELETE FROM bookings WHERE DATE(booked_at) = :d"), {"d": target_date})

            # Платежи
            for pt in ["cash", "terminal", "qr", "transfer", "invoice", "installment"]:
                amount = float(data.get(pt, 0) or 0)
                if amount > 0:
                    session.add(DailyPayment(type="sale", payment_type=pt, amount=amount, created_at=target_date))

            # Продажи
            for _ in range(int(data.get("sales_count", 0) or 0)):
                session.add(Sale(sold_at=target_date))

            # Предзаказы
            for _ in range(int(data.get("preorders_count", 0) or 0)):
                session.add(Preorder(created_at=target_date))

            # Брони (item_id=0 — безопасно)
            bookings_count = int(data.get("bookings_count", 0) or 0)
            for _ in range(bookings_count):
                session.add(Booking(
                    item_id=0,
                    total_amount=0,
                    booked_at=target_date
                ))

    logger.info(f"✅ Статистика за {target_date} успешно обновлена")
    return JSONResponse({"success": True})


@router.get("/top_models_data")
async def top_models_data(request: Request, days: int = 7, target_date: str | None = None):
    end_date = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else datetime.now().date()
    start_date = end_date - timedelta(days=days)

    async_session = get_async_session_factory()
    async with async_session() as session:
        top = (await session.execute(
            select(Item.text, func.count(Sale.id).label("count"))
            .join(Sale, Sale.item_id == Item.id)
            .where(func.date(Sale.sold_at).between(start_date, end_date))
            .group_by(Item.text)
            .order_by(func.count(Sale.id).desc())
            .limit(5)
        )).all()

    return JSONResponse({
        "labels": [row.text for row in top],
        "counts": [row.count for row in top],
    })
