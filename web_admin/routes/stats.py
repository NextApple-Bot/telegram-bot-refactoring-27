from datetime import date

from fastapi import APIRouter, Query, Request
from web_admin.templates import templates

router = APIRouter()


@router.get("/")
async def stats_page(
    request: Request,
    target_date: str | None = None,
    days: int = Query(7, ge=1, le=365),
    mode: str = Query("preset"),
    month: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
):
    # Если дата не передана — берём сегодня
    if not target_date:
        target_date = date.today().isoformat()

    return templates.TemplateResponse(
        "stats.html",
        {
            "request": request,
            "mode": mode,
            "target_date": target_date,
            "days": days,
            "month": month,
            "date_from": date_from,
            "date_to": date_to,
            "sales_count": 0,
            "preorders_count": 0,
            "bookings_count": 0,
            "payment_labels": [],
            "payment_values": [],
            "chart_dates": [],
            "chart_revenue": [],
        },
    )
