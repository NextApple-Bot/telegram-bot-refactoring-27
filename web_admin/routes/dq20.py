        top = (
            await session.execute(
                select(Item.text, func.count(Sale.id).label("count"))
                .select_from(Sale)
                .outerjoin(Item, Item.id == Sale.item_id)
                .where(func.date(Sale.sold_at).between(start_date, end_date))
                .group_by(Item.text)
                .order_by(func.count(Sale.id).desc())
                .limit(5)
            )
        ).all()

    return JSONResponse(
        {
            "labels": [row.text or "—" for row in top],
            "counts": [row.count for row in top],
        }
    )
