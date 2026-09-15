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
    build_day_reconciliation,
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

LOW_STOCK_FAMILIES = (
    "iphone",
    "ipad",
    "samsung",
    "airpods",
    "airpod",
    "apple watch",
    "watch",
)

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
        if free != 0:
            continue
        candidate_ids.append(cat_id)
        meta[cat_id] = {
            "name": name_clean,
            "free": free,
            "booked": booked,
            "total": free + booked,
            "level": "critical",
        }

    if not candidate_ids:
        return []
