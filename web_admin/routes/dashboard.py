from datetime import datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select, text

from bot.db import get_async_session_factory
from bot.models import Booking, Category, DailyPayment, Item, Preorder, Sale, Seller, SellerDay
from web_admin.templates import templates

router = APIRouter()


def get_date_range(target_date: str | None = None):
    if target_date:
        today = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        today = datetime.now().date()
    return today


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, target_date: str | None = None):
    today = get_date_range(target_date)
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    async_session = get_async_session_factory()
    async with async_session() as session:
        # === Продажи сегодня ===
        sales_today = (await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == today)
        )).scalar() or 0

        sales_yesterday = (await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == yesterday)
        )).scalar() or 0

        # === Выручка сегодня ===
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
            'cash': payment_rows.cash or 0,
            'terminal': payment_rows.terminal or 0,
            'qr': payment_rows.qr or 0,
            'transfer': payment_rows.transfer or 0,
            'invoice': payment_rows.invoice or 0,
            'installment': payment_rows.installment or 0,
        }
        revenue_today = sum(payments.values())

        # Выручка вчера
        revenue_yesterday_rows = (await session.execute(
            select(func.coalesce(func.sum(DailyPayment.amount), 0))
            .where(func.date(DailyPayment.created_at) == yesterday)
        )).scalar() or 0

        # === Предзаказы и брони ===
        preorders_today = (await session.execute(
            select(func.count(Preorder.id)).where(func.date(Preorder.created_at) == today)
        )).scalar() or 0

        bookings_today = (await session.execute(
            select(func.count(Booking.id)).where(func.date(Booking.booked_at) == today)
        )).scalar() or 0

        # === Графики за 7 дней ===
        chart_dates = []
        chart_sales = []
        chart_revenue = []

        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            chart_dates.append(d.strftime("%d.%m"))

            sales_count = (await session.execute(
                select(func.count(Sale.id)).where(func.date(Sale.sold_at) == d)
            )).scalar() or 0
            chart_sales.append(sales_count)

            rev = (await session.execute(
                select(func.coalesce(func.sum(DailyPayment.amount), 0))
                .where(func.date(DailyPayment.created_at) == d)
            )).scalar() or 0
            chart_revenue.append(float(rev))

        # === Продавцы ===
        sellers_rows = (await session.execute(
            select(Seller.id, Seller.name, SellerDay.id.isnot(None).label('present'))
            .outerjoin(SellerDay, (Seller.id == SellerDay.seller_id) & (SellerDay.date == today))
            .order_by(Seller.name)
        )).all()

        sellers = [{"id": r.id, "name": r.name, "present": bool(r.present)} for r in sellers_rows]

    # Расчёты изменений
    sales_change_yesterday = round(((sales_today - sales_yesterday) / sales_yesterday * 100), 1) if sales_yesterday > 0 else None
    revenue_change_yesterday = round(((revenue_today - revenue_yesterday_rows) / revenue_yesterday_rows * 100), 1) if revenue_yesterday_rows > 0 else None

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "target_date": today.strftime("%d.%m.%Y"),
        "target_date_iso": today.isoformat(),
        "sales_today": sales_today,
        "revenue_today": revenue_today,
        "sales_change_yesterday": sales_change_yesterday,
        "revenue_change_yesterday": revenue_change_yesterday,
        "payments": payments,
        "stats": {
            "sales_count": sales_today,
            "preorders_count": preorders_today,
            "bookings_count": bookings_today
        },
        "sellers": sellers,
        "chart_dates": chart_dates,
        "chart_sales": chart_sales,
        "chart_revenue": chart_revenue,
        "plan_amount": 600000,
    })


@router.post("/toggle_seller_day")
async def toggle_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
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
    async with async_session() as session, session.begin():
        await session.execute(text("DELETE FROM daily_payments WHERE DATE(created_at) = :d"), {"d": target_date})
        await session.execute(text("DELETE FROM sales WHERE DATE(sold_at) = :d"), {"d": target_date})
        await session.execute(text("DELETE FROM preorders WHERE DATE(created_at) = :d"), {"d": target_date})
        await session.execute(text("DELETE FROM bookings WHERE DATE(booked_at) = :d"), {"d": target_date})

        for pt in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
            amount = float(data.get(pt, 0))
            if amount > 0:
                session.add(DailyPayment(type='sale', payment_type=pt, amount=amount, created_at=target_date))

        for _ in range(int(data.get("sales_count", 0))):
            session.add(Sale(sold_at=target_date))
        for _ in range(int(data.get("preorders_count", 0))):
            session.add(Preorder(created_at=target_date))
        for _ in range(int(data.get("bookings_count", 0))):
            session.add(Booking(item_id=0, booked_at=target_date))

    return JSONResponse({"success": True})
