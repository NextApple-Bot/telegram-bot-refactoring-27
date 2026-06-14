import logging
from datetime import date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import DailyPayment, Sale, Seller, SellerDay
from bot.repositories.stats import StatsRepository
from bot.services.assortment import AssortmentService
from bot.services.cache import cache
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


async def get_dashboard_data(target_date: date) -> dict[str, Any]:
    async_session = get_async_session_factory()

    async with async_session() as session:
        stats = await StatsRepository.get_today_stats()

        revenue_today = stats.get("revenue", 0)
        plan_amount = int(stats.get("plan_amount", 600000))
        fulfillment = round((revenue_today / plan_amount * 100), 1) if plan_amount > 0 else 0

        payments = stats.get("payments", {
            "cash": 0, "terminal": 0, "qr": 0,
            "transfer": 0, "invoice": 0, "installment": 0
        })

        sellers_query = (
            select(Seller.id, Seller.name)
            .join(SellerDay, Seller.id == SellerDay.seller_id)
            .where(SellerDay.date == target_date)
        )
        sellers_result = await session.execute(sellers_query)
        sellers = sellers_result.all()

        seven_days_ago = target_date - timedelta(days=6)
        chart_query = (
            select(
                func.date(DailyPayment.created_at).label("day"),
                func.sum(DailyPayment.amount).label("total")
            )
            .where(DailyPayment.created_at >= seven_days_ago)
            .group_by(func.date(DailyPayment.created_at))
            .order_by(func.date(DailyPayment.created_at))
        )
        chart_result = await session.execute(chart_query)
        chart_data = {str(row.day): float(row.total) for row in chart_result.all()}

    return {
        "target_date": target_date,
        "stats": stats,
        "revenue_today": revenue_today,
        "plan_amount": plan_amount,
        "fulfillment": fulfillment,
        "payments": payments,
        "sellers": sellers,
        "chart_data": chart_data,
    }


@router.get("/", response_class=HTMLResponse)
@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, target_date: str | None = None):
    try:
        selected_date = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else date.today()
    except (ValueError, TypeError):
        selected_date = date.today()

    try:
        data = await get_dashboard_data(selected_date)
    except Exception as e:
        logger.exception("Ошибка загрузки данных дашборда")
        raise HTTPException(status_code=500, detail="Не удалось загрузить данные дашборда") from e

    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, **data, "today": date.today()},
    )


@router.post("/stats/edit")
@router.post("/update_stats")
async def edit_stats(request: Request):
    """Редактирование статистики (возвращает JSON для JS)."""
    form = await request.form()

    target_date_str = form.get("target_date") or date.today().isoformat()

    try:
        edit_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError:
        edit_date = date.today()

    logger.info(f"Редактирование статистики за {edit_date}")

    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            await cache.delete(f"dashboard:summary:{edit_date.isoformat()}")

    await AssortmentService.invalidate_cache()

    # Возвращаем JSON, чтобы JavaScript не падал на редиректе
    return {"success": True, "message": "Статистика обновлена", "target_date": edit_date.isoformat()}


@router.post("/sellers/add")
async def add_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    try:
        work_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")

    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            existing = await session.execute(
                select(SellerDay).where(
                    SellerDay.seller_id == seller_id,
                    SellerDay.date == work_date
                )
            )
            if not existing.scalar_one_or_none():
                session.add(SellerDay(seller_id=seller_id, date=work_date))

    return RedirectResponse(url=f"/admin/dashboard?target_date={target_date}", status_code=303)


@router.post("/sellers/remove")
async def remove_seller_day(seller_id: int = Form(...), target_date: str = Form(...)):
    try:
        work_date = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")

    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            await session.execute(
                SellerDay.__table__.delete().where(
                    SellerDay.seller_id == seller_id,
                    SellerDay.date == work_date
                )
            )

    return RedirectResponse(url=f"/admin/dashboard?target_date={target_date}", status_code=303)
