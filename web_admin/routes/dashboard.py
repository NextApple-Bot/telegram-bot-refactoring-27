from datetime import datetime, timedelta
import os
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select

from bot.db import get_async_session_factory
from bot.models import (
    Category,
    Item,
    Sale,
    Seller,
    SellerDay,
    StatsAdjustment,
)
from web_admin.services.day_stats import (
    ALL_METRICS,
    PAYMENT_METRICS,
    day_snapshot,
    load_adjustments_detail,
    month_totals,
    now_local,
    raw_bookings_count,
    raw_payments,
    raw_preorders_count,
    raw_sales_count,
    today_local,
)
from web_admin.templates import templates
from web_admin.services.audit import log_admin_action

import logging

logger = logging.getLogger(__name__)

router = APIRouter()

DEFAULT_SELLERS = ("Тимофей", "Максим")

LOW_STOCK_THRESHOLD = max(0, int(os.getenv("LOW_STOCK_THRESHOLD", "3")))
SKIP_CATEGORY_NAMES = {"б/у", "б/у:", "ns", "ns:", "общее", "общее:"}

# Только эти семейства в блоке «Мало на складе»
LOW_STOCK_FAMILIES = (
    "iphone",
    "ipad",
    "samsung",
    "airpods",
    "airpod",
    "apple watch",
    "watch",
)

# Серийник в скобках / в конце строки; бронь-пометка
_SERIAL_PARENS = re.compile(r"\(\s*[A-Z0-9]{8,}\s*\)", re.IGNORECASE)
_BOOKING_MARK = re.compile(r"\s*\(Бронь от [^)]+\)\s*", re.IGNORECASE)


async def _ensure_default_sellers(session) -> None:
    for name in DEFAULT_SELLERS:
        exists = (
            await session.execute(
                select(Seller.id).where(func.lower(Seller.name) == func.lower(name))
            )
        ).scalar_one_or_none()
        if not exists:
            session.add(Seller(name=name))


def calculate_change(current: int | float, previous: int | float) -> float | None:
    if previous == 0:
        return None
    return round(((current - previous) / previous) * 100, 1)


def _parse_number(value) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return 0.0


def _is_low_stock_family(category_name: str) -> bool:
    n = (category_name or "").strip().lower().rstrip(":")
    if not n or n in SKIP_CATEGORY_NAMES:
        return False
    for fam in LOW_STOCK_FAMILIES:
        if n == fam or n.startswith(fam + " ") or n.startswith(fam):
            return True
    return False


def _variant_label(text: str | None, serial: str | None = None) -> str:
    """Текст модели без серийника — цвет / память / SIM."""
    t = (text or "").strip()
    if not t:
        return "—"
    t = _BOOKING_MARK.sub(" ", t)
    t = _SERIAL_PARENS.sub(" ", t)
    if serial:
        t = re.sub(re.escape(serial), " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" ,.;")
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"[)\]]+$", "", t).strip(" ,.;")
    t = re.sub(r"\s+", " ", t).strip(" ,.;")
    return t or (text or "—").strip()


async def _low_stock_alerts(session, threshold: int) -> list[dict]:
    free_q = (
        select(
            Category.id,
            Category.name,
            func.count(Item.id).label("free_count"),
        )
        .select_from(Category)
        .outerjoin(
            Item,
            (Item.category_id == Category.id) & (Item.is_booked.is_(False)),
        )
        .group_by(Category.id, Category.name)
        .order_by(func.count(Item.id).asc(), Category.name)
    )
    rows = (await session.execute(free_q)).all()

    booked_q = (
        select(Category.id, func.count(Item.id))
        .select_from(Category)
        .join(Item, (Item.category_id == Category.id) & (Item.is_booked.is_(True)))
        .group_by(Category.id)
    )
    booked_map = {cid: int(c) for cid, c in (await session.execute(booked_q)).all()}

    candidate_ids: list[int] = []
    meta: dict[int, dict] = {}
    for cat_id, name, free_count in rows:
        name_clean = (name or "").strip()
        if not _is_low_stock_family(name_clean):
            continue
        free = int(free_count or 0)
        booked = booked_map.get(cat_id, 0)
        if free == 0 and booked == 0:
            continue
        if free <= threshold:
            candidate_ids.append(cat_id)
            meta[cat_id] = {
                "name": name_clean,
                "free": free,
                "booked": booked,
                "total": free + booked,
                "level": "critical" if free == 0 else "warning",
            }

    if not candidate_ids:
        return []

    items_q = await session.execute(
        select(Item.category_id, Item.text, Item.serial).where(
            Item.category_id.in_(candidate_ids),
            Item.is_booked.is_(False),
        )
    )
    variants_map: dict[int, dict[str, int]] = {cid: {} for cid in candidate_ids}
    for cat_id, text, serial in items_q.all():
        label = _variant_label(text, serial)
        variants_map[cat_id][label] = variants_map[cat_id].get(label, 0) + 1

    alerts = []
    for cat_id in candidate_ids:
        m = meta[cat_id]
        variants = [
            {"name": name, "count": cnt}
            for name, cnt in sorted(
                variants_map.get(cat_id, {}).items(),
                key=lambda x: (x[1], x[0].lower()),
            )
        ]
        alerts.append(
            {
                "id": cat_id,
                "name": m["name"],
                "free": m["free"],
                "booked": m["booked"],
                "total": m["total"],
                "level": m["level"],
                "variants": variants,
            }
        )
    return alerts


@router.get("/")
async def dashboard(request: Request, target_date: str | None = None):
    try:
        today = (
            today_local()
            if not target_date
            else datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        )
    except ValueError:
        today = today_local()

    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    week_ago = today - timedelta(days=7)
    real_today = today_local()

    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            await _ensure_default_sellers(session)

        snap = await day_snapshot(session, today)
        snap_y = await day_snapshot(session, yesterday)
        snap_w = await day_snapshot(session, week_ago)
        month = await month_totals(session, today)

        sales_today = snap["sales_count"]
        revenue_today = snap["total_revenue"]

        sales_change_yesterday = calculate_change(sales_today, snap_y["sales_count"])
        sales_change_week = calculate_change(sales_today, snap_w["sales_count"])
        revenue_change_yesterday = calculate_change(
            float(revenue_today), float(snap_y["total_revenue"])
        )
        revenue_change_week = calculate_change(
            float(revenue_today), float(snap_w["total_revenue"])
        )

        payments = snap["payments"]
        total_revenue = snap["total_revenue"]

        active_bookings = (
            await session.execute(
                select(func.count(Item.id)).where(Item.is_booked.is_(True))
            )
        ).scalar() or 0

        chart_dates, chart_sales, chart_revenue = [], [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            s = await day_snapshot(session, d)
            chart_dates.append(d.strftime("%d.%m"))
            chart_sales.append(s["sales_count"])
            chart_revenue.append(float(s["total_revenue"]))

        sellers_rows = (
            await session.execute(
                select(Seller.id, Seller.name, SellerDay.id.isnot(None).label("present"))
                .outerjoin(
                    SellerDay,
                    (Seller.id == SellerDay.seller_id) & (SellerDay.date == today),
                )
                .order_by(Seller.name)
            )
        ).all()
        sellers = [
            {"id": r.id, "name": r.name, "present": bool(r.present)}
            for r in sellers_rows
        ]

        top_models = (
            await session.execute(
                select(Item.text, func.count(Sale.id).label("count"))
                .select_from(Sale)
                .outerjoin(Item, Item.id == Sale.item_id)
                .where(func.date(Sale.sold_at) >= today - timedelta(days=7))
                .group_by(Item.text)
                .order_by(func.count(Sale.id).desc())
                .limit(5)
            )
        ).all()
        top_labels = [row.text or "—" for row in top_models if row.text]
        top_counts = [row.count for row in top_models if row.text]

        has_adjustments = bool(snap["adjustments"])

        low_stock = await _low_stock_alerts(session, LOW_STOCK_THRESHOLD)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "target_date": today.strftime("%d.%m.%Y"),
            "target_date_iso": today.isoformat(),
            "yesterday_iso": yesterday.isoformat(),
            "tomorrow_iso": tomorrow.isoformat(),
            "real_today_iso": real_today.isoformat(),
            "is_today": today == real_today,
            "sales_today": sales_today,
            "revenue_today": total_revenue,
            "sales_change_yesterday": sales_change_yesterday,
            "sales_change_week": sales_change_week,
            "revenue_change_yesterday": revenue_change_yesterday,
            "revenue_change_week": revenue_change_week,
            "payments": payments,
            "total_revenue": total_revenue,
            "plan_amount": 600000,
            "stats": {
                "sales_count": snap["sales_count"],
                "preorders_count": snap["preorders_count"],
                "bookings_count": snap["bookings_count"],
                "active_bookings": active_bookings,
            },
            "has_adjustments": has_adjustments,
            "sellers": sellers,
            "chart_dates": chart_dates,
            "chart_sales": chart_sales,
            "chart_revenue": chart_revenue,
            "top_labels": top_labels,
            "top_counts": top_counts,
            "days": 7,
            "low_stock": low_stock,
            "low_stock_threshold": LOW_STOCK_THRESHOLD,
            "month": month,
        },
    )


@router.post("/toggle_seller_day")
async def toggle_seller_day(
    seller_id: int = Form(...), target_date: str = Form(...)
):
    try:
        date_obj = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверная дата"}, status_code=400)

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        existing = (
            await session.execute(
                select(SellerDay).where(
                    SellerDay.seller_id == seller_id, SellerDay.date == date_obj
                )
            )
        ).scalar_one_or_none()

        if existing:
            await session.delete(existing)
            status = "removed"
        else:
            session.add(SellerDay(seller_id=seller_id, date=date_obj))
            status = "added"

    return {"success": True, "status": status}


@router.post("/update_stats")
async def update_stats(request: Request):
    logger.info(
        "update_stats: method=%s path=%s auth=%s",
        request.method,
        request.url.path,
        bool(request.session.get("authenticated")),
    )

    try:
        data = await request.json()
    except Exception as e:
        logger.warning("update_stats: bad JSON: %s", e)
        return JSONResponse(
            {"success": False, "error": "Некорректный JSON"},
            status_code=400,
        )

    target_date_str = data.get("target_date")
    if not target_date_str:
        return JSONResponse(
            {"success": False, "error": "target_date is required"},
            status_code=400,
        )

    try:
        target_date = datetime.strptime(str(target_date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse(
            {"success": False, "error": f"Неверная дата: {target_date_str}"},
            status_code=400,
        )

    reason = (data.get("reason") or "").strip() or None

    def _num(key: str) -> float:
        return _parse_number(data.get(key, 0))

    def _int(key: str) -> int:
        return max(0, int(round(_parse_number(data.get(key, 0)))))

    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            raw_sales = await raw_sales_count(session, target_date)
            raw_pre = await raw_preorders_count(session, target_date)
            raw_book = await raw_bookings_count(session, target_date)
            raw_pay = await raw_payments(session, target_date)

            targets = {
                "sales_count": float(_int("sales_count")),
                "preorders_count": float(_int("preorders_count")),
                "bookings_count": float(_int("bookings_count")),
            }
            for pt in PAYMENT_METRICS:
                targets[pt] = max(0.0, _num(pt))

            bases = {
                "sales_count": float(raw_sales),
                "preorders_count": float(raw_pre),
                "bookings_count": float(raw_book),
                **{k: float(raw_pay.get(k, 0)) for k in PAYMENT_METRICS},
            }

            await session.execute(
                delete(StatsAdjustment).where(
                    StatsAdjustment.target_date == target_date
                )
            )

            written = 0
            for metric in ALL_METRICS:
                base = bases.get(metric, 0.0)
                target = targets.get(metric, 0.0)
                delta = target - base
                if abs(delta) < 1e-9:
                    continue
                session.add(
                    StatsAdjustment(
                        target_date=target_date,
                        metric=metric,
                        base_value=base,
                        target_value=target,
                        delta=delta,
                        reason=reason,
                        updated_at=now_local().replace(tzinfo=None),
                    )
                )
                written += 1

            logger.info(
                "Корректировки за %s: %s метрик (Sale/платежи не трогали)",
                target_date,
                written,
            )

        await log_admin_action(
            "update_stats",
            request=request,
            date=str(target_date),
            reason=reason,
        )
        return JSONResponse(
            {
                "success": True,
                "mode": "adjustment",
                "target_date": target_date.isoformat(),
                "message": "Сохранено как корректировка. Реальные продажи не удалялись.",
            }
        )

    except Exception as e:
        logger.exception("Ошибка update_stats за %s", target_date_str)
        return JSONResponse(
            {"success": False, "error": str(e)[:500]},
            status_code=500,
        )


@router.post("/close_day")
async def close_day(request: Request):
    try:
        data = await request.json()
    except Exception as e:
        return JSONResponse({"success": False, "error": f"Некорректный JSON: {e}"}, status_code=400)

    target_date_str = data.get("target_date")
    if not target_date_str:
        return JSONResponse({"success": False, "error": "target_date is required"}, status_code=400)
    try:
        target_date = datetime.strptime(str(target_date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверная дата"}, status_code=400)

    reason = (data.get("reason") or "").strip() or "закрытие дня"
    seller_ids_raw = data.get("seller_ids") or []
    try:
        seller_ids = sorted({int(x) for x in seller_ids_raw})
    except (TypeError, ValueError):
        return JSONResponse({"success": False, "error": "seller_ids must be int list"}, status_code=400)

    def _num(key: str) -> float:
        return _parse_number(data.get(key, 0))

    def _int(key: str) -> int:
        return max(0, int(round(_parse_number(data.get(key, 0)))))

    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            raw_sales = await raw_sales_count(session, target_date)
            raw_pre = await raw_preorders_count(session, target_date)
            raw_book = await raw_bookings_count(session, target_date)
            raw_pay = await raw_payments(session, target_date)

            targets = {
                "sales_count": float(_int("sales_count")),
                "preorders_count": float(_int("preorders_count")),
                "bookings_count": float(_int("bookings_count")),
            }
            for pt in PAYMENT_METRICS:
                targets[pt] = max(0.0, _num(pt))

            bases = {
                "sales_count": float(raw_sales),
                "preorders_count": float(raw_pre),
                "bookings_count": float(raw_book),
                **{k: float(raw_pay.get(k, 0)) for k in PAYMENT_METRICS},
            }

            await session.execute(
                delete(StatsAdjustment).where(StatsAdjustment.target_date == target_date)
            )
            written = 0
            for metric in ALL_METRICS:
                base = bases.get(metric, 0.0)
                target = targets.get(metric, 0.0)
                delta = target - base
                if abs(delta) < 1e-9:
                    continue
                session.add(
                    StatsAdjustment(
                        target_date=target_date,
                        metric=metric,
                        base_value=base,
                        target_value=target,
                        delta=delta,
                        reason=reason,
                        updated_at=now_local().replace(tzinfo=None),
                    )
                )
                written += 1

            await session.execute(
                delete(SellerDay).where(SellerDay.date == target_date)
            )
            for sid in seller_ids:
                seller = await session.get(Seller, sid)
                if seller:
                    session.add(SellerDay(seller_id=sid, date=target_date))

            logger.info(
                "close_day %s: adj=%s, sellers=%s",
                target_date, written, seller_ids,
            )

        await log_admin_action(
            "close_day",
            request=request,
            date=str(target_date),
            adjustments=written,
            sellers=len(seller_ids),
        )
        return JSONResponse({
            "success": True,
            "target_date": target_date.isoformat(),
            "adjustments": written,
            "sellers": len(seller_ids),
            "message": "День закрыт: цифры и смены сохранены.",
        })
    except Exception as e:
        logger.exception("close_day error")
        return JSONResponse({"success": False, "error": str(e)[:500]}, status_code=500)


@router.get("/adjustments")
async def list_adjustments(target_date: str):
    try:
        day = datetime.strptime(str(target_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "bad date"}, status_code=400)
    async_session = get_async_session_factory()
    async with async_session() as session:
        rows = await load_adjustments_detail(session, day)
    return JSONResponse({"success": True, "target_date": day.isoformat(), "items": rows})


@router.get("/top_models_data")
async def top_models_data(
    request: Request, days: int = 7, target_date: str | None = None
):
    end_date = (
        datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        if target_date
        else today_local()
    )
    start_date = end_date - timedelta(days=days)

    async_session = get_async_session_factory()
    async with async_session() as session:
        top = (
            await session.execute(
                select(Item.text, func.count(Sale.id).label("count"))
                .select_from(Sale)
                .outerjoin(Item, Item.id == Sale.item_id)
                .where(func.date(Sale.sold_at).between(start_date, end_date))
                .group_by(Item.text)
                .order_by(func.count(Sale.id).desc())
                .limit(5)
            )
        ).all()

    return JSONResponse(
        {
            "labels": [row.text or "—" for row in top],
            "counts": [row.count for row in top],
        }
    )
