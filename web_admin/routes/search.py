"""
Поиск по серийному номеру в админ-панели.
Статусы: в наличии / бронь / продан.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import aliased

from bot.db import get_async_session_factory
from bot.models import Category, DeletedItem, Item
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


def _norm_serial(value: str | None) -> str:
    return (value or "").strip().upper()


@router.get("/")
async def search_page(
    request: Request,
    q: str = Query("", max_length=120),
):
    """Страница поиска по серийнику / фрагменту текста."""
    query = (q or "").strip()
    results: list[dict[str, Any]] = []

    if query:
        results = await _search(query)

    return templates.TemplateResponse(
        "search.html",
        {
            "request": request,
            "q": query,
            "results": results,
            "count": len(results),
        },
    )


@router.get("/api")
async def search_api(
    q: str = Query("", max_length=120),
):
    """JSON API для быстрого поиска (поле в шапке)."""
    query = (q or "").strip()
    if len(query) < 2:
        return JSONResponse({"ok": True, "results": [], "count": 0})

    results = await _search(query)
    return JSONResponse({"ok": True, "results": results, "count": len(results)})


async def _search(query: str) -> list[dict[str, Any]]:
    """
    Ищем:
    1) items по serial (точное / частичное)
    2) items по text ILIKE (если похоже на SN в тексте)
    3) deleted_items по serial (проданные)
    """
    q_upper = _norm_serial(query)
    q_like = f"%{query}%"
    serial_like = f"%{q_upper}%"
    results: list[dict[str, Any]] = []
    seen_serials: set[str] = set()

    async_session = get_async_session_factory()
    async with async_session() as session:
        # --- В наличии / бронь ---
        cat = aliased(Category)
        stock_q = (
            select(Item, cat.name)
            .outerjoin(cat, Item.category_id == cat.id)
            .where(
                or_(
                    func.upper(Item.serial) == q_upper,
                    Item.serial.ilike(serial_like),
                    Item.text.ilike(q_like),
                )
            )
            .order_by(Item.id.desc())
            .limit(40)
        )
        stock_rows = (await session.execute(stock_q)).all()

        for item, cat_name in stock_rows:
            serial = _norm_serial(item.serial)
            if serial:
                seen_serials.add(serial)

            if item.is_booked:
                status = "booked"
                status_label = "Бронь"
            else:
                status = "in_stock"
                status_label = "В наличии"

            results.append(
                {
                    "status": status,
                    "status_label": status_label,
                    "serial": serial or "—",
                    "text": item.text or "",
                    "category": cat_name or "",
                    "item_id": item.id,
                    "is_booked": bool(item.is_booked),
                    "booking_full_name": item.booking_full_name or "",
                    "booking_phone": item.booking_phone or "",
                    "booking_platform": item.booking_platform or "",
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "source": "items",
                    "link": f"/admin/assortment",
                }
            )

        # --- Проданные (deleted_items) ---
        sold_q = (
            select(DeletedItem)
            .where(
                or_(
                    func.upper(DeletedItem.serial) == q_upper,
                    DeletedItem.serial.ilike(serial_like),
                    DeletedItem.text.ilike(q_like),
                )
            )
            .order_by(DeletedItem.deleted_at.desc())
            .limit(40)
        )
        sold_rows = (await session.execute(sold_q)).scalars().all()

        for di in sold_rows:
            serial = _norm_serial(di.serial)
            # если тот же serial снова в наличии — всё равно покажем продажу как историю
            reason = (di.reason or "").lower()
            if "sale" in reason or not reason:
                status = "sold"
                status_label = "Продан"
            else:
                status = "sold"
                status_label = f"Удалён ({di.reason})" if di.reason else "Продан"

            results.append(
                {
                    "status": status,
                    "status_label": status_label,
                    "serial": serial or "—",
                    "text": di.text or "",
                    "category": "",
                    "item_id": di.id,
                    "original_item_id": di.item_id,
                    "is_booked": False,
                    "reason": di.reason or "",
                    "deleted_at": di.deleted_at.isoformat() if di.deleted_at else None,
                    "sale_message_id": di.sale_message_id,
                    "source": "deleted",
                    "link": "/admin/sold",
                }
            )

    # Точные совпадения serial — выше
    def sort_key(r: dict) -> tuple:
        exact = 0 if _norm_serial(r.get("serial")) == q_upper else 1
        status_ ord = {"in_stock": 0, "booked": 1, "sold": 2}.get(r.get("status"), 9)
        return (exact, status_ord)

    results.sort(key=sort_key)
    return results[:50]
