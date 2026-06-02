from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import Booking, DailyPayment, Preorder, Sale, Seller, SellerDay
from web_admin.templates import templates

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
async def dashboard(request: Request, target_date: str | None = None):
    """Главная страница дашборда с реальными метриками."""
    try:
        today = date.today() if not target_date else datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        today = date.today()

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            # === Продажи за день ===
            sales_count = (await session.execute(
                select(func.count(Sale.id)).where(func.date(Sale.sold_at) == today)
            )).scalar() or 0

            # === Платежи ===
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
                'cash': float(payment_rows.cash or 0),
                'terminal': float(payment_rows.terminal or 0),
                'qr': float(payment_rows.qr or 0),
                'transfer': float(payment_rows.transfer or 0),
                'invoice': float(payment_rows.invoice or 0),
                'installment': float(payment_rows.installment or 0),
            }
            total_revenue = sum(payments.values())
            plan_amount = 600000

            # === Предзаказы и брони ===
            preorders_count = (await session.execute(
                select(func.count(Preorder.id)).where(func.date(Preorder.created_at) == today)
            )).scalar() or 0

            bookings_count = (await session.execute(
                select(func.count(Booking.id)).where(func.date(Booking.booked_at) == today)
            )).scalar() or 0

            # === Графики за 7 дней ===
            dates_labels: list[str] = []
            sales_chart: list[int] = []
            revenue_chart: list[float] = []

            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                dates_labels.append(d.strftime("%d.%m"))

                cnt = (await session.execute(
                    select(func.count(Sale.id)).where(func.date(Sale.sold_at) == d)
                )).scalar() or 0
                sales_chart.append(cnt)

                rev = (await session.execute(
                    select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(func.date(DailyPayment.created_at) == d)
                )).scalar() or 0
                revenue_chart.append(float(rev))

            # === Продавцы дня ===
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
                "plan_amount": plan_amount,
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

        except SQLAlchemyError as e:
            logger.error(f"Ошибка при загрузке дашборда: {e}")
            raise


@router.post("/toggle_seller_day")
async def toggle_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    """Переключение присутствия продавца на дашборде."""
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверный формат даты"}, status_code=400)

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
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
        except SQLAlchemyError as e:
            logger.error(f"Ошибка toggle_seller_day: {e}")
            return JSONResponse({"success": False, "error": "Ошибка базы данных"}, status_code=500)


@router.post("/update_stats")
async def update_stats(request: Request):
    """
    Ручное редактирование статистики за день.
    Полностью без хака с Item(id=0) и __SYSTEM__.
    Использует отдельные delete() через SQLAlchemy.
    """
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Неверный JSON"}, status_code=400)

    target_date_str = data.get("target_date")
    if not target_date_str:
        return JSONResponse({"success": False, "error": "target_date is required"}, status_code=400)

    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверный формат даты"}, status_code=400)

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                # === Очистка старых данных (через SQLAlchemy delete) ===
                await session.execute(
                    delete(DailyPayment).where(func.date(DailyPayment.created_at) == target_date)
                )
                await session.execute(
                    delete(Sale).where(func.date(Sale.sold_at) == target_date)
                )
                await session.execute(
                    delete(Preorder).where(func.date(Preorder.created_at) == target_date)
                )
                await session.execute(
                    delete(Booking).where(func.date(Booking.booked_at) == target_date)
                )

                # Платежи
                for pt in ['cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment']:
                    amount = float(data.get(pt, 0) or 0)
                    if amount > 0:
                        session.add(DailyPayment(
                            type='
