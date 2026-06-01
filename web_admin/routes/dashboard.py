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

    async_session = get_async_session_factory()
    async with async_session() as session:
        # Продажи
        sales_today = (await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == today)
        )).scalar() or 0

        sales_yesterday = (await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == yesterday)
        )).scalar() or 0

        # Платежи сегодня
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
        revenue_yesterday = (await session.execute(
            select(func.coalesce(func.sum(DailyPayment.amount), 0))
            .where(func.date(DailyPayment.created_at) == yesterday)
        )).scalar() or 0

        # Предзаказы и брони
        preorders_today = (await session.execute(
            select(func.count(Preorder.id)).where(func.date(Preorder.created_at) == today)
        )).scalar() or 0

        bookings_today = (await session.execute(
            select(func.count(Booking.id)).where(func.date(Booking.booked_at) == today)
        )).scalar() or 0

        # Графики за 7 дней
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

        # Продавцы
        sellers_rows = (await session.execute(
            select(Seller.id, Seller.name, SellerDay.id.isnot(None).label('present'))
            .outerjoin(SellerDay, (Seller.id == SellerDay.seller_id) & (SellerDay.date == today))
            .order_by(Seller.name)
        )).all()

        sellers = [{"id": r.id, "name": r.name, "present": bool(r.present)} for r in sellers_rows]

    # Изменения
    sales_change = round(((sales_today - sales_yesterday) / sales_yesterday * 100), 1) if sales_yesterday > 0 else None
    revenue_change = round(((revenue_today - revenue_yesterday) / revenue_yesterday * 100), 1) if revenue_yesterday > 0 else None

    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "target_date": today.strftime("%d.%m.%Y"),
        "target_date_iso": today.isoformat(),
        "sales_today": sales_today,
        "revenue_today": revenue_today,
        "sales_change_yesterday": sales_change,
        "revenue_change_yesterday": revenue_change,
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

    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверный формат даты"}, status_code=400)

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        # Очищаем старые данные
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

        # Служебная категория и товар для броней
        sys_cat = (await session.execute(select(Category).where(Category.name == '__SYSTEM__'))).scalar_one_or_none()
        if not sys_cat:
            sys_cat = Category(name='__SYSTEM__', sort_order=-1)
            session.add(sys_cat)
            await session.flush()

        sys_item = (await session.execute(select(Item).where(Item.id == 0))).scalar_one_or_none()
        if not sys_item:
            sys_item = Item(id=0, text='__SYSTEM_STATS__', category_id=sys_cat.id, is_booked=False)
            session.add(sys_item)
            await session.flush()

        for _ in range(int(data.get("bookings_count", 0) or 0)):
            session.add(Booking(item_id=0, booked_at=target_date))

    return JSONResponse({"success": True})


@router.get("/top_models_data")
async def top_models_data(request: Request, days: int = 7, target_date: str | None = None):
    return JSONResponse({"labels": [], "counts": []})
