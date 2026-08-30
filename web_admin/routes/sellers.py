from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import List

from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete, func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import (
    Booking,
    DailyPayment,
    Preorder,
    Sale,
    Seller,
    SellerDay,
    StatsAdjustment,
)
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()

DEFAULT_SELLERS = ("Тимофей", "Максим")
PAYMENT_METRICS = ("cash", "terminal", "qr", "transfer", "invoice", "installment")


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


# ─── Единый снимок дня (как на дашборде) ───────────────────────────────────

async def _load_adjustments(session, day: date) -> dict[str, float]:
    rows = (
        await session.execute(
            select(StatsAdjustment.metric, StatsAdjustment.delta).where(
                StatsAdjustment.target_date == day
            )
        )
    ).all()
    return {m: float(d or 0) for m, d in rows}


async def _raw_sales_count(session, day: date) -> int:
    from_sales = (
        await session.execute(
            select(func.count(Sale.id)).where(func.date(Sale.sold_at) == day)
        )
    ).scalar() or 0
    from_payments = (
        await session.execute(
            select(func.count(DailyPayment.id)).where(
                func.date(DailyPayment.created_at) == day,
                DailyPayment.type == "sale",
            )
        )
    ).scalar() or 0
    return int(max(from_sales, from_payments))


async def _raw_preorders_count(session, day: date) -> int:
    from_payments = (
        await session.execute(
            select(func.count(DailyPayment.id)).where(
                func.date(DailyPayment.created_at) == day,
                DailyPayment.type == "preorder",
            )
        )
    ).scalar() or 0
    from_table = (
        await session.execute(
            select(func.count(Preorder.id)).where(func.date(Preorder.created_at) == day)
        )
    ).scalar() or 0
    return int(max(from_payments, from_table))


async def _raw_bookings_count(session, day: date) -> int:
    return int(
        (
            await session.execute(
                select(func.count(Booking.id)).where(func.date(Booking.booked_at) == day)
            )
        ).scalar()
        or 0
    )


async def _raw_payments(session, day: date) -> dict[str, float]:
    payment_rows = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "cash"
                    ),
                    0,
                ).label("cash"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "terminal"
                    ),
                    0,
                ).label("terminal"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "qr"
                    ),
                    0,
                ).label("qr"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "transfer"
                    ),
                    0,
                ).label("transfer"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "invoice"
                    ),
                    0,
                ).label("invoice"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "installment"
                    ),
                    0,
                ).label("installment"),
            ).where(func.date(DailyPayment.created_at) == day)
        )
    ).one()
    return {
        col: float(getattr(payment_rows, col, 0) or 0) for col in PAYMENT_METRICS
    }


async def _day_snapshot(session, day: date) -> dict:
    """Тот же снимок дня, что и на дашборде: raw + StatsAdjustment."""
    adj = await _load_adjustments(session, day)

    raw_sales = await _raw_sales_count(session, day)
    raw_pre = await _raw_preorders_count(session, day)
    raw_book = await _raw_bookings_count(session, day)
    raw_pay = await _raw_payments(session, day)

    sales = max(0, int(round(raw_sales + adj.get("sales_count", 0))))
    preorders = max(0, int(round(raw_pre + adj.get("preorders_count", 0))))
    bookings = max(0, int(round(raw_book + adj.get("bookings_count", 0))))

    payments = {}
    for k in PAYMENT_METRICS:
        payments[k] = max(0.0, float(raw_pay.get(k, 0) + adj.get(k, 0)))

    return {
        "sales_count": sales,
        "preorders_count": preorders,
        "bookings_count": bookings,
        "payments": payments,
        "total_revenue": sum(payments.values()),
    }


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
    """Статистика по продавцам за период: дни работы, продажи и выручка в их смены.

    Использует тот же снимок дня, что и дашборд (raw + StatsAdjustment),
    чтобы цифры совпадали.
    """
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

            # Кэш снимков по дням, чтобы не считать дважды
            snapshot_cache: dict[date, dict] = {}

            async def snap(d: date) -> dict:
                if d not in snapshot_cache:
                    snapshot_cache[d] = await _day_snapshot(session, d)
                return snapshot_cache[d]

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

                for wd in work_days:
                    s = await snap(wd)
                    sales_count += s["sales_count"]
                    revenue += float(s["total_revenue"])

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

                s = await snap(day)
                calendar_rows.append(
                    {
                        "date": day.isoformat(),
                        "date_display": day.strftime("%d.%m.%Y"),
                        "sellers": list(day_sellers),
                        "sales": s["sales_count"],
                        "revenue": float(s["total_revenue"]),
                    }
                )
                day += timedelta(days=1)

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


# ====================== ГРАФИК СМЕН (массовая отметка) ======================

@router.get("/schedule")
async def seller_schedule(
    request: Request,
    month: str | None = None,
    seller_id: int | None = None,
):
    """
    Упрощённый режим: выбрать продавца → отметить несколько дней месяца.
    """
    today = date.today()
    try:
        if month:
            y, m = map(int, month.split("-"))
            first = date(y, m, 1)
        else:
            first = today.replace(day=1)
    except (ValueError, TypeError):
        first = today.replace(day=1)

    if first.month == 12:
        last = date(first.year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(first.year, first.month + 1, 1) - timedelta(days=1)

    prev_month = (first - timedelta(days=1)).replace(day=1)
    next_month = (last + timedelta(days=1)).replace(day=1)

    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
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

        worked_dates: set[str] = set()
        if selected:
            rows = (
                await session.execute(
                    select(SellerDay.date).where(
                        SellerDay.seller_id == selected.id,
                        SellerDay.date.between(first, last),
                    )
                )
            ).scalars().all()
            worked_dates = {d.isoformat() for d in rows}

        days_grid: list[list[dict | None]] = []
        week: list[dict | None] = []
        for _ in range(first.weekday()):
            week.append(None)

        d = first
        while d <= last:
            iso = d.isoformat()
            week.append(
                {
                    "date": iso,
                    "day": d.day,
                    "worked": iso in worked_dates,
                    "is_today": d == today,
                    "weekday": d.weekday(),
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

        ru_months = {
            1: "Январь",
            2: "Февраль",
            3: "Март",
            4: "Апрель",
            5: "Май",
            6: "Июнь",
            7: "Июль",
            8: "Август",
            9: "Сентябрь",
            10: "Октябрь",
            11: "Ноябрь",
            12: "Декабрь",
        }
        month_label_ru = f"{ru_months.get(first.month, first.strftime('%B'))} {first.year}"

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
    """
    Сохраняет набор дней продавца за месяц.
    Body JSON: { seller_id, month: YYYY-MM, dates: ["YYYY-MM-DD", ...] }
    Заменяет все смены продавца в этом месяце на переданный список.
    """
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
