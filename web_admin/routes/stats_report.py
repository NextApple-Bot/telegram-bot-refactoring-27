from datetime import date, timedelta
import json

from sqlalchemy import func, or_, select

from bot.models import (
    Booking,
    Client,
    DailyPayment,
    DeletedItem,
    Item,
    Preorder,
    Purchase,
    Sale,
)
from web_admin.routes.stats_helpers import (
    PAYMENT_METRICS,
    load_adjustments_range,
    normalize_sold_model,
    normalize_source,
)


async def collect_report(session, start_date: date, end_date: date) -> dict:
    sales_data = await session.execute(
        select(
            func.coalesce(func.sum(Sale.cash), 0).label("cash"),
            func.coalesce(func.sum(Sale.terminal), 0).label("terminal"),
            func.coalesce(func.sum(Sale.qr), 0).label("qr"),
            func.coalesce(func.sum(Sale.transfer), 0).label("transfer"),
            func.coalesce(func.sum(Sale.invoice), 0).label("invoice"),
            func.coalesce(func.sum(Sale.installment), 0).label("installment"),
            func.count(Sale.id).label("count"),
        ).where(func.date(Sale.sold_at).between(start_date, end_date))
    )
    sales_row = dict(sales_data.mappings().one())

    dp_row = (
        await session.execute(
            select(
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "cash"), 0
                ).label("cash"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "terminal"), 0
                ).label("terminal"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "qr"), 0
                ).label("qr"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "transfer"), 0
                ).label("transfer"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(DailyPayment.payment_type == "invoice"), 0
                ).label("invoice"),
                func.coalesce(
                    func.sum(DailyPayment.amount).filter(
                        DailyPayment.payment_type == "installment"
                    ),
                    0,
                ).label("installment"),
            ).where(func.date(DailyPayment.created_at).between(start_date, end_date))
        )
    ).mappings().one()

    for k in PAYMENT_METRICS:
        sales_row[k] = max(float(sales_row.get(k) or 0), float(dp_row.get(k) or 0))

    sales_from_dp = (
        await session.execute(
            select(func.count(DailyPayment.id)).where(
                func.date(DailyPayment.created_at).between(start_date, end_date),
                DailyPayment.type == "sale",
            )
        )
    ).scalar() or 0
    sales_row["count"] = int(max(int(sales_row["count"] or 0), int(sales_from_dp)))

    preorders_data = await session.execute(
        select(
            func.coalesce(func.sum(Preorder.cash), 0).label("cash"),
            func.coalesce(func.sum(Preorder.terminal), 0).label("terminal"),
            func.coalesce(func.sum(Preorder.qr), 0).label("qr"),
            func.coalesce(func.sum(Preorder.transfer), 0).label("transfer"),
            func.coalesce(func.sum(Preorder.invoice), 0).label("invoice"),
            func.coalesce(func.sum(Preorder.installment), 0).label("installment"),
            func.count(Preorder.id).label("count"),
        ).where(func.date(Preorder.created_at).between(start_date, end_date))
    )
    preorders_row = dict(preorders_data.mappings().one())

    pre_from_dp = (
        await session.execute(
            select(func.count(DailyPayment.id)).where(
                func.date(DailyPayment.created_at).between(start_date, end_date),
                DailyPayment.type == "preorder",
            )
        )
    ).scalar() or 0
    preorders_row["count"] = int(max(int(preorders_row["count"] or 0), int(pre_from_dp)))

    bookings_data = await session.execute(
        select(
            func.coalesce(func.sum(Booking.total_amount), 0).label("total"),
            func.count(Booking.id).label("count"),
        ).where(func.date(Booking.booked_at).between(start_date, end_date))
    )
    bookings_row = dict(bookings_data.mappings().one())

    adj = await load_adjustments_range(session, start_date, end_date)
    totals_adj = adj["totals"]
    by_day_adj = adj["by_day"]

    sales_row["count"] = max(
        0, int(round(float(sales_row["count"]) + totals_adj.get("sales_count", 0)))
    )
    acc_raw = (
        await session.execute(
            select(func.coalesce(func.sum(Sale.count), 0)).where(
                func.date(Sale.sold_at).between(start_date, end_date),
                Sale.is_accessory.is_(True),
            )
        )
    ).scalar() or 0
    accessories_count = max(
        0, int(round(float(acc_raw) + totals_adj.get("accessories_count", 0)))
    )
    devices_count = max(0, int(sales_row["count"]) - accessories_count)
    sales_row["accessories_count"] = accessories_count
    sales_row["devices_count"] = devices_count

    preorders_row["count"] = max(
        0, int(round(float(preorders_row["count"]) + totals_adj.get("preorders_count", 0)))
    )
    bookings_row["count"] = max(
        0, int(round(float(bookings_row["count"]) + totals_adj.get("bookings_count", 0)))
    )
    for k in PAYMENT_METRICS:
        sales_row[k] = max(0.0, float(sales_row.get(k) or 0) + totals_adj.get(k, 0.0))

    sales_by_day = {
        row.d: int(row.cnt)
        for row in (
            await session.execute(
                select(
                    func.date(Sale.sold_at).label("d"),
                    func.count(Sale.id).label("cnt"),
                )
                .where(func.date(Sale.sold_at).between(start_date, end_date))
                .group_by(func.date(Sale.sold_at))
            )
        ).all()
    }
    dp_sales_by_day = {
        row.d: int(row.cnt)
        for row in (
            await session.execute(
                select(
                    func.date(DailyPayment.created_at).label("d"),
                    func.count(DailyPayment.id).label("cnt"),
                )
                .where(
                    func.date(DailyPayment.created_at).between(start_date, end_date),
                    DailyPayment.type == "sale",
                )
                .group_by(func.date(DailyPayment.created_at))
            )
        ).all()
    }
    revenue_by_day = {
        row.d: float(row.amt or 0)
        for row in (
            await session.execute(
                select(
                    func.date(DailyPayment.created_at).label("d"),
                    func.coalesce(func.sum(DailyPayment.amount), 0).label("amt"),
                )
                .where(func.date(DailyPayment.created_at).between(start_date, end_date))
                .group_by(func.date(DailyPayment.created_at))
            )
        ).all()
    }

    chart_dates: list[str] = []
    chart_sales: list[int] = []
    chart_revenue: list[float] = []
    current = start_date
    while current <= end_date:
        chart_dates.append(current.strftime("%d.%m"))
        raw_sales = max(
            int(sales_by_day.get(current, 0) or 0),
            int(dp_sales_by_day.get(current, 0) or 0),
        )
        day_adj = by_day_adj.get(current, {})
        adj_sales = float(day_adj.get("sales_count", 0))
        chart_sales.append(max(0, int(round(raw_sales + adj_sales))))
        raw_rev = float(revenue_by_day.get(current, 0) or 0)
        adj_rev = sum(float(day_adj.get(k, 0)) for k in PAYMENT_METRICS)
        chart_revenue.append(max(0.0, raw_rev + adj_rev))
        current += timedelta(days=1)

    purchase_rows = (
        await session.execute(
            select(
                Client.referral_source,
                Client.social_network,
                Purchase.total_amount,
                Purchase.purchase_type,
                Purchase.items_json,
            )
            .select_from(Purchase)
            .outerjoin(Client, Client.id == Purchase.client_id)
            .where(func.date(Purchase.created_at).between(start_date, end_date))
        )
    ).all()

    source_agg: dict[str, dict] = {}
    model_agg: dict[str, dict] = {}

    for ref, social, amount, ptype, items_json in purchase_rows:
        src = normalize_source(ref or social)
        if src not in source_agg:
            source_agg[src] = {"count": 0, "amount": 0.0}
        source_agg[src]["count"] += 1
        source_agg[src]["amount"] += float(amount or 0)

        items = []
        if items_json:
            try:
                raw = json.loads(items_json) if isinstance(items_json, str) else items_json
                if isinstance(raw, list):
                    items = raw
                elif isinstance(raw, dict):
                    items = [raw]
            except Exception:
                items = []
        for it in items:
            raw_name = (it.get("item_text") or it.get("text") or it.get("name") or "").strip()
            name = normalize_sold_model(raw_name)
            if not name:
                continue
            price = float(it.get("price") or 0)
            if name not in model_agg:
                model_agg[name] = {"count": 0, "amount": 0.0}
            model_agg[name]["count"] += 1
            model_agg[name]["amount"] += price

    deleted_rows = (
        await session.execute(
            select(DeletedItem.text, func.count(DeletedItem.id))
            .where(
                func.date(DeletedItem.deleted_at).between(start_date, end_date),
                or_(
                    DeletedItem.reason.ilike("%sale%"),
                    DeletedItem.reason == "sale_history",
                    DeletedItem.sale_message_id.isnot(None),
                ),
                DeletedItem.restored.is_(False),
            )
            .group_by(DeletedItem.text)
        )
    ).all()
    deleted_agg: dict[str, int] = {}
    for raw_text, cnt in deleted_rows:
        name = normalize_sold_model(raw_text or "")
        if not name:
            continue
        deleted_agg[name] = deleted_agg.get(name, 0) + int(cnt or 0)
    for name, cnt in deleted_agg.items():
        if name not in model_agg:
            model_agg[name] = {"count": 0, "amount": 0.0}
        model_agg[name]["count"] = max(model_agg[name]["count"], cnt)

    booking_platform_rows = (
        await session.execute(
            select(Item.booking_platform, func.count(Item.id))
            .where(Item.is_booked.is_(True))
            .group_by(Item.booking_platform)
        )
    ).all()
    booking_sources: dict[str, int] = {}
    for plat, cnt in booking_platform_rows:
        src = normalize_source(plat)
        booking_sources[src] = booking_sources.get(src, 0) + int(cnt or 0)

    sources_sorted = sorted(source_agg.items(), key=lambda x: x[1]["amount"], reverse=True)
    models_sorted = sorted(model_agg.items(), key=lambda x: x[1]["count"], reverse=True)[:50]

    return {
        "sales_row": sales_row,
        "preorders_row": preorders_row,
        "bookings_row": bookings_row,
        "chart_dates": chart_dates,
        "chart_sales": chart_sales,
        "chart_revenue": chart_revenue,
        "source_labels": [k for k, _ in sources_sorted],
        "source_counts": [v["count"] for _, v in sources_sorted],
        "source_amounts": [round(v["amount"], 0) for _, v in sources_sorted],
        "sources_table": [
            {"name": n, "count": d["count"], "amount": d["amount"]}
            for n, d in sources_sorted
        ],
        "booking_sources_table": sorted(
            [{"name": k, "count": v} for k, v in booking_sources.items()],
            key=lambda x: x["count"],
            reverse=True,
        ),
        "models_table": [
            {"name": n, "count": d["count"], "amount": d["amount"]}
            for n, d in models_sorted
        ],
        "model_labels": [n for n, _ in models_sorted[:10]],
        "model_counts": [d["count"] for _, d in models_sorted[:10]],
        "has_adjustments": bool(totals_adj),
    }
