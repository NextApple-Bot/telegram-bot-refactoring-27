from datetime import date, datetime, timedelta
from io import BytesIO
import json
import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import func, or_, select

from bot.db import get_async_session_factory
from bot.models import (
    Booking,
    Client,
    DailyPayment,
    DeletedItem,
    Item,
    Preorder,
    Purchase,
    Sale,
    StatsAdjustment,
)
from web_admin.templates import templates

router = APIRouter()

MAX_RANGE_DAYS = 366

PAYMENT_METRICS = ("cash", "terminal", "qr", "transfer", "invoice", "installment")
COUNT_METRICS = ("sales_count", "preorders_count", "bookings_count")


def _normalize_source(raw: str | None) -> str:
    if not raw:
        return "Не указан"
    s = re.sub(r"\s+", " ", str(raw).strip())
    if not s:
        return "Не указан"
    low = s.lower()
    mapping = [
        (("авито", "avito"), "Авито"),
        (("telegram", "телеграм", "тг", "tg"), "Telegram"),
        (("whatsapp", "ватсап", "вацап", "wa"), "WhatsApp"),
        (("знакомые", "посоветовали", "рекоменд", "сарафан"), "Рекомендации"),
        (("уже покупали", "повтор", "постоянн"), "Уже покупали"),
        (("instagram", "инстаграм", "инста"), "Instagram"),
        (("youtube", "ютуб"), "YouTube"),
        (("сайт", "site", "web"), "Сайт"),
        (("офлайн", "магазин", "пришёл", "пришел"), "Офлайн / магазин"),
    ]
    for keys, label in mapping:
        if any(k in low for k in keys):
            return label
    return s[:40] if len(s) > 40 else s


def normalize_sold_model(text: str) -> str:
    """Модель + память, без цвета и SN."""
    s = (text or "").strip()
    if not s:
        return ""
    low = s.lower()
    if low.startswith(("trade", "трейд", "гнц", "uds", "налич", "терминал", "qr", "перевод")):
        return ""
    if "trade-in" in low or "trade in" in low or "трейд" in low:
        return ""
    s = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    mem = None
    m = re.search(r"(\d+)\s*/\s*(\d+)\s*(GB|TB|гб|тб)\b", s, re.I)
    if m:
        unit = m.group(3).upper().replace("ГБ", "GB").replace("ТБ", "TB")
        mem = f"{m.group(2)}{unit}"
    else:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(GB|TB|гб|тб)\b", s, re.I)
        if m:
            num = m.group(1).replace(",", ".")
            try:
                f = float(num)
                num = str(int(f)) if f == int(f) else num
            except ValueError:
                pass
            unit = m.group(2).upper().replace("ГБ", "GB").replace("ТБ", "TB")
            mem = f"{num}{unit}"
    parts = [p.strip() for p in s.split(",") if p.strip()]
    model = parts[0] if parts else s
    model = re.sub(r"\s*\d+\s*/\s*\d+\s*(GB|TB|гб|тб)\b", "", model, flags=re.I)
    model = re.sub(r"\s*\d+(?:[.,]\d+)?\s*(GB|TB|гб|тб)\b", "", model, flags=re.I)
    model = re.sub(r"\s+", " ", model).strip(" -")
    if not model:
        return ""
    return f"{model} {mem}" if mem else model


def _safe_parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
