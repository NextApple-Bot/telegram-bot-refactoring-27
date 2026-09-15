                select(Seller.id, Seller.name, SellerDay.id.isnot(None).label("present"))
                .outerjoin(
                    SellerDay,
                    (Seller.id == SellerDay.seller_id) & (SellerDay.date == today),
                )
                .order_by(Seller.name)
            )
        ).all()
        sellers = [
            {"id": r.id, "name": r.name, "present": bool(r.present)}
            for r in sellers_rows
        ]

        top_models = (
            await session.execute(
                select(Item.text, func.count(Sale.id).label("count"))
                .select_from(Sale)
                .outerjoin(Item, Item.id == Sale.item_id)
                .where(func.date(Sale.sold_at) >= today - timedelta(days=7))
                .group_by(Item.text)
                .order_by(func.count(Sale.id).desc())
                .limit(5)
            )
        ).all()
        top_labels = [row.text or "—" for row in top_models if row.text]
        top_counts = [row.count for row in top_models if row.text]
        top_models_list = [
            {"model": row.text or "—", "count": row.count}
            for row in top_models
            if row.text
        ]

