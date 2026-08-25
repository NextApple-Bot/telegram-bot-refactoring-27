import logging
from datetime import date

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, select

from bot.db import get_async_session_factory
from bot.models import DailyPayment, DeletedItem, Item, Sale
from bot.services.assortment import AssortmentService
from bot.services.cache import cache
from web_admin.templates import templates

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/")
async def list_sold(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
):
    async_session = get_async_session_factory()
    async with async_session() as session:
        offset = (page - 1) * per_page

        count_q = (
            select(func.count())
            .select_from(DeletedItem)
            .where(DeletedItem.reason == "sale_from_admin")
        )
        total = (await session.execute(count_q)).scalar() or 0

        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        q = (
            select(DeletedItem)
            .where(DeletedItem.reason == "sale_from_admin")
            .order_by(DeletedItem.deleted_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        items = (await session.execute(q)).scalars().all()

    return templates.TemplateResponse(
        "sold.html",
        {
            "request": request,
            "items": items,
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    )


@router.post("/restore/{item_id}")
async def restore_sold(item_id: int):
    """
    Восстановить товар в ассортимент и откатить статистику продажи:
    - вернуть Item
    - удалить DeletedItem
    - удалить Sale (по sale_message_id / item_id)
    - удалить DailyPayment (по sale_message_id)
    """
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        deleted = await session.get(DeletedItem, item_id)
        if not deleted:
            return RedirectResponse(url="/admin/sold", status_code=303)

        sale_message_id = deleted.sale_message_id
        original_item_id = deleted.item_id

        # 1. Вернуть товар в ассортимент
        session.add(
            Item(
                text=deleted.text,
                serial=deleted.serial,
                category_id=deleted.category_id,
                is_booked=False,
            )
        )

        # 2. Удалить запись о продаже (Sale)
        if sale_message_id:
            await session.execute(
                delete(Sale).where(Sale.message_id == sale_message_id)
            )
            # 3. Удалить платежи, привязанные к этой продаже
            await session.execute(
                delete(DailyPayment).where(
                    DailyPayment.sale_message_id == sale_message_id
                )
            )
        elif original_item_id:
            # fallback: по item_id, если message_id не сохранился
            await session.execute(
                delete(Sale).where(Sale.item_id == original_item_id)
            )

        # 4. Убрать из «проданных»
        await session.delete(deleted)

        logger.info(
            "Восстановлен товар deleted_id=%s item_id=%s sale_message_id=%s",
            item_id,
            original_item_id,
            sale_message_id,
        )

    # Сбросить кэш дашборда / ассортимента
    try:
        await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
    except Exception:
        pass
    await AssortmentService.invalidate_cache()

    return RedirectResponse(url="/admin/sold", status_code=303)
