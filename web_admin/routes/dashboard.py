import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select, text

from bot.db import get_async_session_factory
from bot.models import (
    Booking, Category, DailyPayment, Item, Preorder, Sale, Seller, SellerDay
)
from bot.repositories.stats import StatsRepository
from bot.services.cache import cache
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, target_date: str | None = None):
    today = datetime.now().date() if not target_date else datetime.strptime(target_date, "%Y-%m-%d").date()

    async_session = get_async_session_factory()
    async with async_session() as session:
        # Продажи
        sales_count = (await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == today)
        )).scalar() or 0

        # Платежи
        payment_rows = (await session.execute(
            select(
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == 'cash'), 0).label('cash'),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == 'terminal'), 0).label('terminal'),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == 'qr'), 0).label('qr'),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == 'transfer'), 0).label('transfer'),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == 'invoice'), 0).label('invoice'),
                func.coalesce(func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == 'installment'), 0).label('installment'),
            ).where(func.date(DailyPayment.created_at) == today)
        )).one()

        payments = {
            "cash": float(getattr(payment_rows, "cash", 0) or 0),
            "terminal": float(getattr(payment_rows, "terminal", 0) or 0),
            "qr": float(getattr(payment_rows, "qr", 0) or 0),
            "transfer": float(getattr(payment_rows, "transfer", 0) or 0),
            "invoice": float(getattr(payment_rows, "invoice", 0) or 0),
            "installment": float(getattr(payment_rows, "installment", 0) or 0),
        }
        total_revenue = sum(payments.values())
        plan = 600000

        # Предзаказы и брони
        preorders_count = (await session.execute(
            select(func.count(Preorder.id)).where(func.date(Preorder.created_at) == today)
        )).scalar() or 0

        bookings_count = (await session.execute(
            select(func.count(Booking.id)).where(func.date(Booking.booked_at) == today)
        )).scalar() or 0

        # Графики за 7 дней
        dates_labels = [(today - timedelta(days=i)).strftime("%d.%m") for i in range(6, -1, -1)]
        sales_chart, revenue_chart = [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            cnt = (await session.execute(
                select(func.count(Sale.id)).where(func.date(Sale.sold_at) == d)
            )).scalar() or 0
            rev = (await session.execute(
                select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(func.date(DailyPayment.created_at) == d)
            )).scalar() or 0
            sales_chart.append(cnt)
            revenue_chart.append(float(rev))

        # Продавцы
        sellers_rows = (await session.execute(
            select(Seller.id, Seller.name, SellerDay.id.isnot(None).label('present'))
            .outerjoin(SellerDay, (Seller.id == SellerDay.seller_id) & (SellerDay.date == today))
            .order_by(Seller.name)
        )).all()
        sellers = [{"id": r.id, "name": r.name, "present": bool(r.present)} for r in sellers_rows]

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "target_date": today.strftime("%d.%m.%Y"),
        "target_date_iso": today.isoformat(),
        "sales_today": sales_count,
        "revenue_today": total_revenue,
        "sales_change_yesterday": 0,
        "sales_change_week": 0,
        "revenue_change_yesterday": 0,
        "revenue_change_week": 0,
        "payments": payments,
        "total_revenue": total_revenue,
        "plan_amount": plan,
        "stats": {
            "sales_count": sales_count,
            "preorders_count": preorders_count,
            "bookings_count": bookings_count
        },
        "sellers": sellers,
        "chart_dates": dates_labels,
        "chart_sales": sales_chart,
        "chart_revenue": revenue_chart,
        "top_labels": [],
        "top_counts": [],
        "days": 7,
    })


@router.post("/update_stats")
async def update_stats(request: Request):
    data = await request.json()
    target_date_str = data.get("target_date")
    if not target_date_str:
        return JSONResponse({"success": False, "error": "target_date is required"}, status_code=400)

    target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        # Очистка старых данных (как в v26)
        await session.execute(text("DELETE FROM daily_payments WHERE DATE(created_at) = :d"), {"d": target_date})
        await session.execute(text("DELETE FROM sales WHERE DATE(sold_at) = :d"), {"d": target_date})
        await session.execute(text("DELETE FROM preorders WHERE DATE(created_at) = :d"), {"d": target_date})
        await session.execute(text("DELETE FROM bookings WHERE DATE(booked_at) = :d"), {"d": target_date})

        # Платежи
        for pt in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
            amount = float(data.get(pt, 0) or 0)
            if amount > 0:
                session.add(DailyPayment(type='sale', payment_type=pt, amount=amount, created_at=target_date))

        # Продажи
        for _ in range(int(data.get("sales_count", 0) or 0)):
            session.add(Sale(sold_at=target_date))

        # Предзаказы
        for _ in range(int(data.get("preorders_count", 0) or 0)):
            session.add(Preorder(created_at=target_date))

        # Брони + системный товар (как в v26)
        sys_item = (await session.execute(select(Item).where(Item.id == 0))).scalar_one_or_none()
        if not sys_item:
            sys_cat = (await session.execute(select(Category).where(Category.name == '__SYSTEM__'))).scalar_one_or_none()
            if not sys_cat:
                sys_cat = Category(name='__SYSTEM__', sort_order=-1)
                session.add(sys_cat)
                await session.flush()
            session.add(Item(id=0, text='__SYSTEM_STATS__', category_id=sys_cat.id, is_booked=False))

        for _ in range(int(data.get("bookings_count", 0) or 0)):
            session.add(Booking(item_id=0, booked_at=target_date))

    await cache.delete(f"dashboard:summary:{target_date.isoformat()}")
    return JSONResponse({"success": True})
