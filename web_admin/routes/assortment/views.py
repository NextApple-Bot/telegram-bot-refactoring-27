import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, func, not_, or_, select

from bot.db import get_async_session_factory
from bot.models import Category, Item
from web_admin.templates import templates

router = APIRouter()

# Разрешённые поля для сортировки (защита от SQL-инъекций)
ALLOWED_SORT_FIELDS = {
    "id": Item.id,
    "text": Item.text,
    "serial": Item.serial,
    "category_name": Category.name,
    "is_booked": Item.is_booked,
    "created_at": Item.created_at,
}

ALLOWED_SIM_TYPES = {"", "esim", "sim_esim"}

# (O) / (О) / （O） — обменка (латиница, кириллица, fullwidth-скобки)
_EXCHANGE_RE = re.compile(
    r"[\(（]\s*[OoОо0]\s*[\)）]"  # (O) (О) (0) и fullwidth
)
# 👨‍🔧 и варианты эмодзи механика
_SERVICE_MARKERS = (
    "\U0001f468\u200d\U0001f527",  # 👨‍🔧 ZWJ
    "\U0001f468\u200d\u2699",       # 👨 + ⚙
    "\U0001f527",                   # 🔧
)


def _item_flags(text: str | None) -> tuple[bool, bool]:
    """Возвращает (is_exchange, is_service) по тексту названия."""
    t = text or ""
    is_exchange = bool(_EXCHANGE_RE.search(t)) or ("обменк" in t.lower())
    is_service = any(m in t for m in _SERVICE_MARKERS) or (
        "\U0001f468" in t and "\U0001f527" in t
    )
    return is_exchange, is_service


def _apply_sim_filter(query, sim_type: str | None):
    """Фильтр по типу SIM в названии товара: eSIM или SIM+eSIM."""
    st = (sim_type or "").strip().lower()
    if st not in ALLOWED_SIM_TYPES or not st:
        return query

    sim_esim_cond = or_(
        Item.text.ilike("%SIM+eSIM%"),
        Item.text.ilike("%SIM + eSIM%"),
        Item.text.ilike("%SIM+ESIM%"),
        Item.text.ilike("%SIM + ESIM%"),
    )

    if st == "sim_esim":
        return query.where(sim_esim_cond)

    if st == "esim":
        return query.where(
            and_(
                Item.text.ilike("%eSIM%"),
                not_(sim_esim_cond),
            )
        )

    return query


@router.get("/", response_class=HTMLResponse)
async def list_assortment(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = Query(None),
    category_id: str | None = Query(None),
    sim_type: str | None = Query(None),
    sort_by: str = Query("id", pattern="^(id|text|serial|category_name|is_booked|created_at)$"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    async_session = get_async_session_factory()
    sim_type_clean = (sim_type or "").strip().lower()
    if sim_type_clean not in ALLOWED_SIM_TYPES:
        sim_type_clean = ""

    async with async_session() as session:
        offset = (page - 1) * per_page

        base_query = (
            select(
                Item.id,
                Item.text,
                Item.serial,
                Item.is_booked,
                Item.created_at,
                Category.id.label("category_id"),
                Category.name.label("category_name"),
            )
            .join(Category, Item.category_id == Category.id)
            .where(Category.name != "__SYSTEM__")
        )

        if search:
            base_query = base_query.where(
                (Item.text.ilike(f"%{search}%")) | (Item.serial.ilike(f"%{search}%"))
            )

        if category_id and category_id.isdigit():
            base_query = base_query.where(Item.category_id == int(category_id))

        base_query = _apply_sim_filter(base_query, sim_type_clean)

        sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Item.id)
        order_direction = sort_column.desc() if sort_order == "desc" else sort_column.asc()
        base_query = base_query.order_by(order_direction).limit(per_page).offset(offset)

        count_query = (
            select(func.count())
            .select_from(Item)
            .join(Category, Item.category_id == Category.id)
            .where(Category.name != "__SYSTEM__")
        )

        if search:
            count_query = count_query.where(
                (Item.text.ilike(f"%{search}%")) | (Item.serial.ilike(f"%{search}%"))
            )
        if category_id and category_id.isdigit():
            count_query = count_query.where(Item.category_id == int(category_id))

        count_query = _apply_sim_filter(count_query, sim_type_clean)

        total = (await session.execute(count_query)).scalar_one()
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1

        items_result = await session.execute(base_query)
        items = []
        for row in items_result.all():
            d = dict(row._mapping)
            is_ex, is_svc = _item_flags(d.get("text"))
            d["is_exchange"] = is_ex
            d["is_service"] = is_svc
            items.append(d)

        cats_query = (
            select(Category.id, Category.name)
            .where(Category.name != "__SYSTEM__")
            .order_by(Category.sort_order, Category.name)
        )
        categories_result = await session.execute(cats_query)
        categories = [dict(row._mapping) for row in categories_result.all()]

    return templates.TemplateResponse(
        "assortment.html",
        {
            "request": request,
            "items": items,
            "page": page,
            "total_pages": total_pages,
            "per_page": per_page,
            "total": total,
            "search": search,
            "category_id": category_id,
            "sim_type": sim_type_clean,
            "categories": categories,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )
