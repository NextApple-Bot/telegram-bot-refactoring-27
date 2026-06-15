import logging
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import DailyPayment, Sale, Seller, SellerDay
from bot.repositories.stats import StatsRepository
from bot.services.cache import cache
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_dashboard_data(target_date: date = None):
    """Получение данных для дашборда (пока только за сегодня)."""
    if target_date is None:
        target_date = date.today()

    async_session = get_async_session_factory()
    async with async_session() as session:
        # Получаем статистику (только за сегодня, как реализовано в репозитории)
        stats = await StatsRepository.get_today_stats()

        # Продавцы на сегодня
        sellers_result = await session.execute(
            select(Seller).join(SellerDay).where(SellerDay.date == target_date)
        )
        sellers = sellers_result.scalars().all()

        # Платежи за сегодня
        payments_result = await session.execute(
            select(DailyPayment.payment_type, func.sum(DailyPayment.amount))
            .where(func.date(DailyPayment.created_at) == target_date)
            .group_by(DailyPayment.payment_type)
        )
        payments = {row[0]: float(row[1] or 0) for row in payments_result.all()}

        revenue_today = sum(payments.values())

        return {
            "target_date": target_date,
            "target_date_iso": target_date.isoformat(),
            "stats": stats,
            "sellers": sellers,
            "payments": payments,
            "revenue_today": revenue_today,
            "sales_today": stats.get("sales_count", 0) if isinstance(stats, dict) else 0,
            "plan_amount": 50000,
        }


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, target_date: str = None):
    """Главная страница дашборда."""
    try:
        if target_date:
            target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
        else:
            target_date_obj = date.today()

        data = await get_dashboard_data(target_date_obj)
        return templates.TemplateResponse("dashboard.html", {"request": request, **data})
    except Exception as e:
        logger.exception("Ошибка при загрузке дашборда")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stats/edit")
@router.post("/update_stats")
async def update_stats(request: Request):
    """Сохранение статистики."""
    try:
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)

        target_date_str = data.get("target_date")
        if not target_date_str:
            return JSONResponse({"success": False, "error": "target_date обязателен"}, status_code=400)

        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            await session.execute(
                "DELETE FROM daily_payments WHERE DATE(created_at) = :d",
                {"d": target_date}
            )

            payment_fields = ["cash", "terminal", "qr", "transfer", "invoice", "installment"]
            for field in payment_fields:
                amount = float(data.get(field, 0) or 0)
                if amount > 0:
                    session.add(DailyPayment(
                        type="sale",
                        payment_type=field,
                        amount=amount,
                        created_at=target_date
                    ))

        await cache.delete(f"dashboard:summary:{target_date.isoformat()}")
        return JSONResponse({"success": True})

    except Exception as e:
        logger.exception("Ошибка при сохранении статистики")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
