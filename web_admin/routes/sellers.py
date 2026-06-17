from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List

from fastapi import APIRouter, Form, Query, Request, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import DailyPayment, Sale, Seller, SellerDay
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/manage")
async def seller_manage(request: Request):
    """Страница управления продавцами."""
    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            sellers = (
                await session.execute(
                    select(Seller).order_by(Seller.name)
                )
            ).scalars().all()

            return templates.TemplateResponse(
                "sellers_manage.html",
                {"request": request, "sellers": sellers}
            )
        except SQLAlchemyError as e:
            logger.error(f"Ошибка при загрузке продавцов: {e}")
            raise HTTPException(status_code=500, detail="Ошибка базы данных")


@router.post("/add")
async def add_seller(request: Request, name: str = Form(...)):
    """Добавление нового продавца."""
    name = name.strip() if name else ""
    if not name:
        raise HTTPException(status_code=400, detail="Имя продавца не может быть пустым")

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                # Проверка на существование
                existing = await session.execute(
                    select(Seller.id).where(func.lower(Seller.name) == func.lower(name))
                )
                if existing.scalar_one_or_none():
                    raise HTTPException(status_code=400, detail="Продавец с таким именем уже существует")

                new_seller = Seller(name=name)
                session.add(new_seller)

            logger.info(f"Добавлен новый продавец: {name}")
            return RedirectResponse(url="/admin/sellers/manage", status_code=303)

        except SQLAlchemyError as e:
            logger.error(f"Ошибка при добавлении продавца '{name}': {e}")
            raise HTTPException(status_code=500, detail="Ошибка при добавлении продавца")


@router.post("/delete/{seller_id}")
async def delete_seller(seller_id: int):
    """Удаление продавца."""
    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            async with session.begin():
                seller = await session.get(Seller, seller_id)
                if not seller:
                    raise HTTPException(status_code=404, detail="Продавец не найден")
                await session.delete(seller)

            logger.info(f"Удалён продавец id={seller_id}")
            return RedirectResponse(url="/admin/sellers/manage", status_code=303)

        except SQLAlchemyError as e:
            logger.error(f"Ошибка при удалении продавца {seller_id}: {e}")
            raise HTTPException(status_code=500, detail="Ошибка при удалении продавца")


@router.get("/stats")
async def seller_stats(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    date_from: str | None = None,
    date_to: str | None = None,
):
    """Статистика продавцов (дни работы + общая статистика за период)."""
    try:
        if date_from and date_to:
            start_date = date.fromisoformat(date_from)
            end_date = date.fromisoformat(date_to)
        else:
            end_date = date.today()
            start_date = end_date - timedelta(days=days - 1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный формат даты")

    async_session = get_async_session_factory()
    async with async_session() as session:
        try:
            # Продавцы + количество дней работы
            sellers_query = (
                select(
                    Seller.id,
                    Seller.name,
                    func.count(func.distinct(SellerDay.date)).label("days_worked"),
                )
                .outerjoin(
                    SellerDay,
                    (Seller.id == SellerDay.seller_id)
                    & (SellerDay.date.between(start_date, end_date)),
                )
                .group_by(Seller.id, Seller.name)
                .order_by(Seller.name)
            )

            sellers_rows = (await session.execute(sellers_query)).all()

            # Общая статистика за период (пока общая, не личная по продавцу)
            total_sales = (
                await session.execute(
                    select(func.count(Sale.id)).where(
                        func.date(Sale.sold_at).between(start_date, end_date)
                    )
                )
            ).scalar() or 0

            total_revenue = (
                await session.execute(
                    select(func.coalesce(func.sum(DailyPayment.amount), 0)).where(
                        func.date(DailyPayment.created_at).between(start_date, end_date)
                    )
                )
            ).scalar() or 0.0

            results: List[dict] = [
                {
                    "id": row.id,
                    "name": row.name,
                    "days_worked": row.days_worked or 0,
                    "total_count": total_sales,
                    "total_revenue": float(total_revenue),
                }
                for row in sellers_rows
            ]

            return templates.TemplateResponse(
                "sellers_stats.html",
                {
                    "request": request,
                    "results": results,
                    "days": days,
                    "date_from": date_from,
                    "date_to": date_to,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                },
            )

        except SQLAlchemyError as e:
            logger.error(f"Ошибка при расчёте статистики продавцов: {e}")
            raise HTTPException(status_code=500, detail="Ошибка базы данных при расчёте статистики")
