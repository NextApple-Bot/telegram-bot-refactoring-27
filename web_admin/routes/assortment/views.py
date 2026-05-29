from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select, update

from bot.db import get_async_session_factory
from bot.models import Category, Item
from web_admin.templates import templates

router = APIRouter()

ALLOWED_SORT_FIELDS = {
    "id": Item.id,
    "text": Item.text,
    "serial": Item.serial,
    "category_name": Category.name,
    "is_booked": Item.is_booked,
    "created_at": Item.created_at,
}

@router.get("/", response_class=HTMLResponse)
async def list_assortment(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = Query(None),
    category_id: str | None = Query(None),
    sort_by: str = Query("id", pattern="^(id|text|serial|category_name|is_booked|created_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    async_session = get_async_session_factory()
    async with async_session() as session:
        offset = (page - 1) * per_page
        base_query = select(
            Item.id, Item.text, Item.serial, Item.is_booked, Item.created_at,
            Category.id.label('category_id'), Category.name.label('category_name')
        ).join(Category, Item.category_id == Category.id).where(Category.name != '__SYSTEM__')

        if search:
            base_query = base_query.where(
                (Item.text.ilike(f"%{search}%")) | (Item.serial.ilike(f"%{search}%"))
            )
        if category_id and category_id.isdigit():
            base_query = base_query.where(Item.category_id == int(category_id))

        sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Item.id)
        order_direction = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        base_query = base_query.order_by(order_direction).limit(per_page).offset(offset)

        count_query = select(func.count()).select_from(Item).join(Category, Item.category_id == Category.id).where(Category.name != '__SYSTEM__')
        if search:
            count_query = count_query.where(
                (Item.text.ilike(f"%{search}%")) | (Item.serial.ilike(f"%{search}%"))
            )
        if category_id and category_id.isdigit():
            count_query = count_query.where(Item.category_id == int(category_id))

        total = (await session.execute(count_query)).scalar()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        items = (await session.execute(base_query)).all()

        cats_q = select(Category.id, Category.name).where(Category.name != '__SYSTEM__').order_by(Category.sort_order, Category.name)
        categories = (await session.execute(cats_q)).all()

    return templates.TemplateResponse("assortment.html", {
        "request": request,
        "items": [dict(i._mapping) for i in items],
        "page": page,
        "total_pages": total_pages,
        "per_page": per_page,
        "total": total,
        "search": search,
        "category_id": category_id,
        "categories": [dict(c._mapping) for c in categories],
        "sort_by": sort_by,
        "sort_order": sort_order,
    })

@router.post("/categories/reorder")
async def reorder_categories(request: Request):
    # Поддержка и form-data, и JSON
    try:
        data = await request.json()
        if isinstance(data, list):
            order = data
        else:
            order = data.get('order', [])
    except:
        form = await request.form()
        order = form.getlist('order[]')

    if not order:
        raise HTTPException(status_code=400, detail="Пустой порядок")

    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        for idx, cat_id in enumerate(order):
            await session.execute(
                update(Category)
                .where(Category.id == int(cat_id))
                .values(sort_order=idx)
            )

    return {"status": "ok"}
