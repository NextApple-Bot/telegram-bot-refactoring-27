import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import and_, func, not_, or_, select

from bot.db import get_async_session_factory
from bot.models import Category, Item
from web_admin.services.sku_parser import build_sku_matrix
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

ALLOWED_SIM_TYPES = {"", "esim", "sim_esim"}
ALLOWED_MARK_TYPES = {"", "exchange", "service", "both", "normal"}

# (O) / (О) / （O） — обменка
_EXCHANGE_RE = re.compile(r"[\(（]\s*[OoОо0]\s*[\)）]")
_SERVICE_MARKERS = (
    "\U0001f468\u200d\U0001f527",  # 👨‍🔧
    "\U0001f468\u200d\u2699",
    "\U0001f527",  # 🔧
)

# SQL: обменка по regex PostgreSQL
_EXCHANGE_SQL = r"[\(（][[:space:]]*[OoОо0][[:space:]]*[\)）]"


def _item_flags(text: str | None) -> tuple[bool, bool]:
    t = text or ""
    is_exchange = bool(_EXCHANGE_RE.search(t)) or ("обменк" in t.lower())
    is_service = any(m in t for m in _SERVICE_MARKERS) or (
        "\U0001f468" in t and "\U0001f527" in t
    )
    return is_exchange, is_service


def _exchange_sql_cond():
    return or_(
        Item.text.op("~")(_EXCHANGE_SQL),
        Item.text.ilike("%обменк%"),
    )


def _service_sql_cond():
    return or_(
        Item.text.like("%\U0001f468\u200d\U0001f527%"),
        Item.text.like("%\U0001f527%"),
    )


def _apply_sim_filter(query, sim_type: str | None):
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


def _apply_mark_filter(query, mark_type: str | None):
    """Фильтр: обменка / сервис / оба / обычные."""
    mt = (mark_type or "").strip().lower()
    if mt not in ALLOWED_MARK_TYPES or not mt:
        return query

    ex = _exchange_sql_cond()
    svc = _service_sql_cond()

    if mt == "exchange":
        return query.where(ex)
    if mt == "service":
        return query.where(svc)
    if mt == "both":
        return query.where(and_(ex, svc))
    if mt == "normal":
        return query.where(and_(not_(ex), not_(svc)))
    return query


@router.get("/", response_class=HTMLResponse)
async def list_assortment(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=10, le=200),
    search: str | None = Query(None),
    category_id: str | None = Query(None),
    sim_type: str | None = Query(None),
    mark_type: str | None = Query(None),
    sort_by: str = Query(
        "id", pattern="^(id|text|serial|category_name|is_booked|created_at)$"
    ),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
):
    async_session = get_async_session_factory()
    sim_type_clean = (sim_type or "").strip().lower()
    if sim_type_clean not in ALLOWED_SIM_TYPES:
        sim_type_clean = ""
    mark_type_clean = (mark_type or "").strip().lower()
    if mark_type_clean not in ALLOWED_MARK_TYPES:
        mark_type_clean = ""

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
        base_query = _apply_mark_filter(base_query, mark_type_clean)

        sort_column = ALLOWED_SORT_FIELDS.get(sort_by, Item.id)
        order_direction = (
            sort_column.desc() if sort_order == "desc" else sort_column.asc()
        )
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
        count_query = _apply_mark_filter(count_query, mark_type_clean)

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
            "mark_type": mark_type_clean,
            "categories": categories,
            "sort_by": sort_by,
            "sort_order": sort_order,
        },
    )


@router.get("/matrix", response_class=HTMLResponse)
async def sku_matrix(
    request: Request,
    category_id: str | None = Query(None),
    only_free: int = Query(0, ge=0, le=1),
):
    """
    Матрица SKU: память × цвет × SIM по выбранной категории.
    Атрибуты парсятся из текста товара (отдельных колонок нет).
    """
    async_session = get_async_session_factory()
    cat_id: int | None = None
    if category_id and str(category_id).isdigit():
        cat_id = int(category_id)

    async with async_session() as session:
        cats_q = (
            select(Category.id, Category.name)
            .where(Category.name != "__SYSTEM__")
            .order_by(Category.sort_order, Category.name)
        )
        categories = [
            dict(r._mapping) for r in (await session.execute(cats_q)).all()
        ]

        selected_name = None
        matrix = {
            "rows": [],
            "memories": [],
            "colors": [],
            "sims": [],
            "total_items": 0,
            "total_free": 0,
            "total_booked": 0,
            "variant_count": 0,
        }

        if cat_id is not None:
            cat = await session.get(Category, cat_id)
            if cat and cat.name != "__SYSTEM__":
                selected_name = cat.name
                items_q = await session.execute(
                    select(Item.id, Item.text, Item.serial, Item.is_booked).where(
                        Item.category_id == cat_id
                    )
                )
                items = [dict(r._mapping) for r in items_q.all()]
                matrix = build_sku_matrix(items)
                if only_free:
                    matrix["rows"] = [r for r in matrix["rows"] if r["free"] > 0]
                    matrix["variant_count"] = len(matrix["rows"])

    return templates.TemplateResponse(
        "assortment_matrix.html",
        {
            "request": request,
            "categories": categories,
            "category_id": str(cat_id) if cat_id is not None else "",
            "selected_name": selected_name,
            "matrix": matrix,
            "only_free": only_free,
        },
    )
