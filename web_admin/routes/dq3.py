        .group_by(Category.id, Category.name)
        .order_by(func.count(Item.id).asc(), Category.name)
    )
    rows = (await session.execute(free_q)).all()

    booked_q = (
        select(Category.id, func.count(Item.id))
        .select_from(Category)
        .join(Item, (Item.category_id == Category.id) & (Item.is_booked.is_(True)))
        .group_by(Category.id)
    )
    booked_map = {cid: int(c) for cid, c in (await session.execute(booked_q)).all()}

    candidate_ids: list[int] = []
    meta: dict[int, dict] = {}
    for cat_id, name, free_count in rows:
        name_clean = (name or "").strip()
        if not _is_low_stock_family(name_clean):
            continue
        free = int(free_count or 0)
        booked = booked_map.get(cat_id, 0)
        if free != 0:
            continue
        candidate_ids.append(cat_id)
        meta[cat_id] = {
            "name": name_clean,
            "free": free,
            "booked": booked,
            "total": free + booked,
            "level": "critical",
        }

    if not candidate_ids:
        return []

    items_q = await session.execute(
        select(Item.category_id, Item.text, Item.serial, Item.is_booked).where(
