from datetime import date, datetime, timedelta
import re

from sqlalchemy import select

from bot.models import StatsAdjustment

MAX_RANGE_DAYS = 366
PAYMENT_METRICS = ("cash", "terminal", "qr", "transfer", "invoice", "installment")
COUNT_METRICS = ("sales_count", "preorders_count", "bookings_count")


def normalize_source(raw: str | None) -> str:
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


def safe_parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def parse_period(target_date, days, mode, month, date_from, date_to):
    today = date.today()
    target = safe_parse_date(target_date) or today
    mode = (mode or "preset").strip().lower()
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 7
    days = max(1, min(days, MAX_RANGE_DAYS))
    if mode == "preset":
        end_date = target
        start_date = end_date - timedelta(days=days - 1)
    elif mode == "month" and month:
        try:
            year, mon = map(int, month.split("-"))
            start_date = date(year, mon, 1)
            if mon == 12:
                end_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                end_date = date(year, mon + 1, 1) - timedelta(days=1)
        except (ValueError, TypeError):
            end_date = today
            start_date = end_date - timedelta(days=6)
    else:
        df = safe_parse_date(date_from)
        dt = safe_parse_date(date_to)
        if df and dt:
            start_date, end_date = df, dt
        elif df and not dt:
            start_date = end_date = df
        elif dt and not df:
            start_date = end_date = dt
        else:
            end_date = today
            start_date = end_date - timedelta(days=6)
    if start_date > end_date:
        start_date, end_date = end_date, start_date
    span = (end_date - start_date).days + 1
    if span > MAX_RANGE_DAYS:
        start_date = end_date - timedelta(days=MAX_RANGE_DAYS - 1)
    period_label = f"{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}"
    return start_date, end_date, period_label


async def load_adjustments_range(session, start_date: date, end_date: date) -> dict:
    rows = (
        await session.execute(
            select(
                StatsAdjustment.target_date,
                StatsAdjustment.metric,
                StatsAdjustment.delta,
            ).where(StatsAdjustment.target_date.between(start_date, end_date))
        )
    ).all()
    by_day: dict = {}
    totals: dict = {}
    for d, metric, delta in rows:
        day = d if isinstance(d, date) else d
        val = float(delta or 0)
        if day not in by_day:
            by_day[day] = {}
        by_day[day][metric] = by_day[day].get(metric, 0.0) + val
        totals[metric] = totals.get(metric, 0.0) + val
    return {"by_day": by_day, "totals": totals}
