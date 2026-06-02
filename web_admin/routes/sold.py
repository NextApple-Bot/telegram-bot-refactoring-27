from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import DeletedItem, Item
from bot.services.assortment import AssortmentService
from web_admin.templates import templates

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

        count_q = select(func.count()).select_from(DeletedItem).where(DeletedItem.reason == 'sale_from_admin')
        total = (await session.execute(count_q)).scalar()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        q = (
            select(DeletedItem)
            .where(DeletedItem.reason == 'sale_from_admin')
            .order_by(DeletedItem.deleted_at.desc())
            .limit(per_page)
            .offset(offset)
        )
        items = (await session.execute(q)).scalars().all()

    return templates.TemplateResponse("sold.html", {
        "request": request,
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    })


@router.post("/restore/{item_id}")
async def restore_sold(item_id: int):
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        deleted = await session.get(DeletedItem, item_id)
        if deleted:
            session.add(Item(
                text=deleted.text,
                serial=deleted.serial,
                category_id=deleted.category_id,
                is_booked=False
            ))
            await session.delete(deleted)

    await AssortmentService.invalidate_cache()
    return RedirectResponse(url="/admin/sold", status_code=303)
