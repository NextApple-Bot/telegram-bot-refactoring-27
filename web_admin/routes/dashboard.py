import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import DailyPayment, Sale, Seller, SellerDay
from bot.repositories.stats import StatsRepository
from bot.services.assortment import AssortmentService
from bot.services.cache import cache
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


# ... (get_dashboard_data и dashboard оставляю как в предыдущей версии)


@router.post("/stats/edit")
@router.post("/update_stats")
async def update_stats(request: Request):
    """
    Универсальный обработчик сохранения статистики.
    Поддерживает и JSON, и form-data.
    """
    try:
        # Пытаемся прочитать JSON (как в v26)
        content_type = request.headers.get("content-type", "")
        if "application/json" in content_type:
            data = await request.json()
        else:
            form = await request.form()
            data = dict(form)

        target_date_str = data.get("target_date")
        if not target_date_str:
            return JSONResponse({"success": False, "error": "target_date обязателен"}, status_code=400)

        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()

        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            # Очищаем старые данные за день (можно расширить)
            await session.execute(
                "DELETE FROM daily_payments WHERE DATE(created_at) = :d", {"d": target_date}
            )

            # Сохраняем платежи
            payment_fields = ["cash", "terminal", "qr", "transfer", "invoice", "installment"]
            for field in payment_fields:
                amount = float(data.get(field, 0) or 0)
                if amount > 0:
                    session.add(DailyPayment(
                        type="sale",
                        payment_type=field,
                        amount=amount,
                        created_at=target_date
                    ))

            # При необходимости здесь можно сохранить sales_count, preorders_count, bookings_count

        await cache.delete(f"dashboard:summary:{target_date.isoformat()}")
        return JSONResponse({"success": True})

    except Exception as e:
        logger.exception("Ошибка при сохранении статистики")
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)
