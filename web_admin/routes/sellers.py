from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import List

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import Seller, SellerDay
from web_admin.services.day_stats import day_snapshot, today_local
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_SELLERS = ("Тимофей", "Максим")


async def ensure_default_sellers(session) -> None:
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
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Имя обязательно")
    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            exists = (
                await session.execute(
                    select(Seller.id).where(func.lower(Seller.name) == func.lower(name))
                )
            ).scalar_one_or_none()
            if exists:
                raise HTTPException(status_code=400, detail="Такой продавец уже есть")
            session.add(Seller(name=name))
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.post("/delete/{seller_id}")
async def delete_seller(seller_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            seller = await session.get(Seller, seller_id)
            if seller:
                await session.delete(seller)
    return RedirectResponse(url="/admin/sellers/manage", status_code=303)


@router.get("/stats")
async def seller_stats(
    request: Request,
    date_from: str | None = None,
    date_to: str | None = None,
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Статистика продавцов за период.

    Форма шлёт date_from/date_to; быстрые ссылки — days=7|30|90.
    start/end оставлены для совместимости.
    """
    t = today_local()

    if days and not date_from and not date_to and not start and not end:
        end_date = t
        start_date = t - timedelta(days=max(1, int(days)) - 1)
    else:
        raw_from = date_from or start
        raw_to = date_to or end
        try:
            start_date = (
                datetime.strptime(str(raw_from)[:10], "%Y-%m-%d").date()
                if raw_from
                else t.replace(day=1)
            )
        except (ValueError, TypeError):
            start_date = t.replace(day=1)
        try:
            end_date = (
                datetime.strptime(str(raw_to)[:10], "%Y-%m-%d").date()
                if raw_to
                else t
            )
        except (ValueError, TypeError):
            end_date = t

    if end_date < start_date:
        start_date, end_date = end_date, start_date

    async_session = get_async_session_factory()
    async with async_session() as session:
        await ensure_default_sellers(session)
        sellers = (
            await session.execute(select(Seller).order_by(Seller.name))
        ).scalars().all()

        snap_cache: dict[date, dict] = {}

        async def snap(d: date) -> dict:
            if d not in snap_cache:
                snap_cache[d] = await day_snapshot(session, d)
            return snap_cache[d]

        days_sellers: dict[date, list[str]] = {}
        all_seller_days = (
            await session.execute(
                select(SellerDay.date, Seller.name)
                .join(Seller, Seller.id == SellerDay.seller_id)
                .where(SellerDay.date.between(start_date, end_date))
                .order_by(SellerDay.date, Seller.name)
            )
        ).all()
        for d, name in all_seller_days:
            days_sellers.setdefault(d, []).append(name)

        seller_rows = []
        for seller in sellers:
            worked = (
                await session.execute(
                    select(SellerDay.date)
                    .where(
                        SellerDay.seller_id == seller.id,
                        SellerDay.date.between(start_date, end_date),
                    )
                    .order_by(SellerDay.date)
                )
            ).scalars().all()
            days_worked = len(worked)
            sales_count = 0
            revenue = 0.0
            accessories_revenue = 0.0
            accessories_count = 0
            # Если в день оба — каждому полный день (как в подписи шаблона)
            for d in worked:
                s = await snap(d)
                sales_count += int(s.get("sales_count", 0) or 0)
                revenue += float(s.get("total_revenue", 0) or 0)
                accessories_revenue += float(s.get("accessories_revenue", 0) or 0)
                accessories_count += int(s.get("accessories_count", 0) or 0)

            avg_check = (revenue / sales_count) if sales_count else 0.0
            sales_per_shift = (sales_count / days_worked) if days_worked else 0.0
            seller_rows.append(
                {
                    "id": seller.id,
                    "name": seller.name,
                    "days_worked": days_worked,
                    "sales_count": sales_count,
                    "revenue": revenue,
                    "accessories_revenue": accessories_revenue,
                    "accessories_count": accessories_count,
                    "avg_check": avg_check,
                    "sales_per_shift": sales_per_shift,
                    "work_dates": [d.isoformat() for d in worked],
                }
            )

        calendar = []
        unassigned_days = []
        d = start_date
        while d <= end_date:
            s = await snap(d)
            names = days_sellers.get(d, [])
            sales = int(s.get("sales_count", 0) or 0)
            rev = float(s.get("total_revenue", 0) or 0)
            acc_rev = float(s.get("accessories_revenue", 0) or 0)
            calendar.append(
                {
                    "date": d.isoformat(),
                    "date_display": d.strftime("%d.%m.%Y"),
                    "sellers": names,
                    "sales": sales,
                    "revenue": rev,
                    "accessories_revenue": acc_rev,
                }
            )
            if (sales or rev) and not names:
                unassigned_days.append(
                    {
                        "date": d.isoformat(),
                        "date_display": d.strftime("%d.%m.%Y"),
                        "sales": sales,
                        "revenue": rev,
                    }
                )
            d += timedelta(days=1)

        return templates.TemplateResponse(
            "sellers_stats.html",
            {
                "request": request,
                "sellers": seller_rows,
                "date_from": start_date.isoformat(),
                "date_to": end_date.isoformat(),
                "calendar": calendar,
                "unassigned_days": unassigned_days,
            },
        )


@router.get("/schedule")
async def seller_schedule(
    request: Request,
    month: str | None = None,
    seller_id: int | None = None,
):
    try:
        if month:
            y, m = map(int, month.split("-"))
            first = date(y, m, 1)
        else:
            t = today_local()
            first = t.replace(day=1)
    except ValueError:
        t = today_local()
        first = t.replace(day=1)

    if first.month == 12:
        last = date(first.year + 1, 1, 1) - timedelta(days=1)
        next_month = date(first.year + 1, 1, 1)
    else:
        last = date(first.year, first.month + 1, 1) - timedelta(days=1)
        next_month = date(first.year, first.month + 1, 1)
    if first.month == 1:
        prev_month = date(first.year - 1, 12, 1)
    else:
        prev_month = date(first.year, first.month - 1, 1)

    month_names = (
        "",
        "Январь",
        "Февраль",
        "Март",
        "Апрель",
        "Май",
        "Июнь",
        "Июль",
        "Август",
        "Сентябрь",
        "Октябрь",
        "Ноябрь",
        "Декабрь",
    )
    month_label_ru = f"{month_names[first.month]} {first.year}"

    async_session = get_async_session_factory()
    async with async_session() as session:
        await ensure_default_sellers(session)

        sellers = (
            await session.execute(select(Seller).order_by(Seller.name))
        ).scalars().all()

        selected = None
        if seller_id:
            selected = await session.get(Seller, seller_id)
        if selected is None and sellers:
            selected = sellers[0]
            seller_id = selected.id

        worked_dates: set[date] = set()
        if selected:
            worked_dates = set(
                (
                    await session.execute(
                        select(SellerDay.date).where(
                            SellerDay.seller_id == selected.id,
                            SellerDay.date.between(first, last),
                        )
                    )
                ).scalars().all()
            )

        today = today_local()
        days_grid: list[list] = []
        week: list = [None] * first.weekday()
        d = first
        while d <= last:
            week.append(
                {
                    "date": d.isoformat(),
                    "day": d.day,
                    "weekday": d.weekday(),
                    "worked": d in worked_dates,
                    "is_today": d == today,
                }
            )
            if len(week) == 7:
                days_grid.append(week)
                week = []
            d += timedelta(days=1)
        if week:
            while len(week) < 7:
                week.append(None)
            days_grid.append(week)

        return templates.TemplateResponse(
            "sellers_schedule.html",
            {
                "request": request,
                "sellers": sellers,
                "selected": selected,
                "seller_id": seller_id,
                "days_grid": days_grid,
                "month": first.strftime("%Y-%m"),
                "month_label": month_label_ru,
                "prev_month": prev_month.strftime("%Y-%m"),
                "next_month": next_month.strftime("%Y-%m"),
                "worked_count": len(worked_dates),
            },
        )


@router.post("/schedule/save")
async def seller_schedule_save(request: Request):
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Некорректный JSON"}, status_code=400)

    seller_id = data.get("seller_id")
    month = data.get("month")
    dates_raw = data.get("dates") or []

    if not seller_id or not month:
        return JSONResponse(
            {"success": False, "error": "seller_id и month обязательны"}, status_code=400
        )

    try:
        y, m = map(int, str(month).split("-"))
        first = date(y, m, 1)
        if m == 12:
            last = date(y + 1, 1, 1) - timedelta(days=1)
        else:
            last = date(y, m + 1, 1) - timedelta(days=1)
    except (ValueError, TypeError):
        return JSONResponse({"success": False, "error": "Неверный month"}, status_code=400)

    parsed_dates: list[date] = []
    for s in dates_raw:
        try:
            d = datetime.strptime(str(s)[:10], "%Y-%m-%d").date()
            if first <= d <= last:
                parsed_dates.append(d)
        except (ValueError, TypeError):
            continue
    parsed_dates = sorted(set(parsed_dates))

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        seller = await session.get(Seller, int(seller_id))
        if not seller:
            return JSONResponse({"success": False, "error": "Продавец не найден"}, status_code=404)

        await session.execute(
            delete(SellerDay).where(
                SellerDay.seller_id == seller.id,
                SellerDay.date.between(first, last),
            )
        )
        for d in parsed_dates:
            session.add(SellerDay(seller_id=seller.id, date=d))

    return JSONResponse(
        {
            "success": True,
            "seller_id": int(seller_id),
            "month": month,
            "count": len(parsed_dates),
            "message": f"Сохранено смен: {len(parsed_dates)}",
        }
    )
