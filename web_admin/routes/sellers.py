from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import DailyPayment, Sale, Seller, SellerDay
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_SELLERS = ("Тимофей", "Максим")


async def ensure_default_sellers(session) -> None:
    """Создаёт Тимофея и Максима, если их ещё нет."""
    for name in DEFAULT_SELLERS:
        exists = (
            await session.execute(
                select(Seller.id).where(func.lower(Seller.name) == func.lower(name))
            )
        ).scalar_one_or_none()
        if not exists:
            session.add(Seller(name=name))
            logger.info("Создан продавец по умолчанию: %s", name)


@router.get("/manage")
async def seller_manage(request: Request):
    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                await ensure_default_sellers(session)

            sellers = (
                await session.execute(select(Seller).order_by(Seller.name))
            ).scalars().all()

            return templates.TemplateResponse(
                "sellers_manage.html",
                {"request": request, "sellers": sellers},
            )
        except SQLAlchemyError as e:
            logger.error("Ошибка при загрузке продавцов: %s", e)
            raise HTTPException(status_code=500, detail="Ошибка базы данных")


@router.post("/add")
async def add_seller(request: Request, name: str = Form(...)):
    name = name.strip() if name else ""
    if not name:
        raise HTTPException(status_code=400, detail="Имя продавца не может быть пустым")

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                existing = await session.execute(
                    select(Seller.id).where(func.lower(Seller.name) == func.lower(name))
                )
                if existing.scalar_one_or_none():
                    raise HTTPException(
                        status_code=400, detail="Продавец с таким именем уже существует"
                    )
                session.add(Seller(name=name))
            return RedirectResponse(url="/admin/sellers/manage", status_code=303)
        except HTTPException:
            raise
        except SQLAlchemyError as e:
            logger.error("Ошибка при добавлении продавца '%s': %s", name, e)
            raise HTTPException(status_code=500, detail="Ошибка при добавлении продавца")


@router.post("/delete/{seller_id}")
async def delete_seller(seller_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                seller = await session.get(Seller, seller_id)
                if not seller:
                    raise HTTPException(status_code=404, detail="Продавец не найден")
                await session.delete(seller)
            return RedirectResponse(url="/admin/sellers/manage", status_code=303)
        except HTTPException:
            raise
        except SQLAlchemyError as e:
            logger.error("Ошибка при удалении продавца %s: %s", seller_id, e)
            raise HTTPException(status_code=500, detail="Ошибка при удалении продавца")


@router.get("/stats")
async def seller_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Статистика по продавцам за период: дни работы, продажи и выручка в их смены."""
    try:
        if date_from and date_to:
            start_date = date.fromisoformat(date_from)
            end_date = date.fromisoformat(date_to)
            if end_date < start_date:
                start_date, end_date = end_date, start_date
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=days - 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                await ensure_default_sellers(session)

            sellers = (
                await session.execute(select(Seller).order_by(Seller.name))
            ).scalars().all()

            results: List[dict] = []
            calendar_rows: List[dict] = []

            for seller in sellers:
                work_days = (
                    await session.execute(
                        select(SellerDay.date)
                        .where(
                            SellerDay.seller_id == seller.id,
                            SellerDay.date.between(start_date, end_date),
                        )
                        .order_by(SellerDay.date)
                    )
                ).scalars().all()

                days_worked = len(work_days)
                sales_count = 0
                revenue = 0.0

                if work_days:
                    sales_count = (
                        await session.execute(
                            select(func.count(Sale.id)).where(
                                func.date(Sale.sold_at).in_(work_days)
                            )
                        )
                    ).scalar() or 0

                    revenue = float(
                        (
                            await session.execute(
                                select(
                                    func.coalesce(func.sum(DailyPayment.amount), 0)
                                ).where(
                                    func.date(DailyPayment.created_at).in_(work_days)
                                )
                            )
                        ).scalar()
                        or 0
                    )

                results.append(
                    {
                        "id": seller.id,
                        "name": seller.name,
                        "days_worked": days_worked,
                        "sales_count": sales_count,
                        "revenue": revenue,
                        "work_dates": [d.isoformat() for d in work_days],
                    }
                )

            # Календарь смен: кто работал в каждый день периода
            day = start_date
            while day <= end_date:
                day_sellers = (
                    await session.execute(
                        select(Seller.name)
                        .join(SellerDay, SellerDay.seller_id == Seller.id)
                        .where(SellerDay.date == day)
                        .order_by(Seller.name)
                    )
                ).scalars().all()

                day_sales = (
                    await session.execute(
                        select(func.count(Sale.id)).where(func.date(Sale.sold_at) == day)
                    )
                ).scalar() or 0

                day_rev = float(
                    (
                        await session.execute(
                            select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(
                                func.date(DailyPayment.created_at) == day
                            )
                        )
                    ).scalar()
                    or 0
                )

                calendar_rows.append(
                    {
                        "date": day.isoformat(),
                        "date_display": day.strftime("%d.%m.%Y"),
                        "sellers": list(day_sellers),
                        "sales": day_sales,
                        "revenue": day_rev,
                    }
                )
                day += timedelta(days=1)

            # Новые дни сверху
            calendar_rows.reverse()

            return templates.TemplateResponse(
                "sellers_stats.html",
                {
                    "request": request,
                    "results": results,
                    "calendar": calendar_rows,
                    "days": days,
                    "date_from": start_date.isoformat(),
                    "date_to": end_date.isoformat(),
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            )
        except SQLAlchemyError as e:
            logger.error("Ошибка статистики продавцов: %s", e)
            raise HTTPException(status_code=500, detail="Ошибка базы данных")
