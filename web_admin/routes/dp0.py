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
