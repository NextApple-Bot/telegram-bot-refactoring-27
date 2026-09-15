            Item.category_id.in_(candidate_ids),
        )
    )
    variants_map: dict[int, dict[str, int]] = {cid: {} for cid in candidate_ids}
    booked_variants_map: dict[int, dict[str, int]] = {cid: {} for cid in candidate_ids}
    for cat_id, text, serial, is_booked in items_q.all():
        label = _variant_label(text, serial)
        if is_booked:
            booked_variants_map[cat_id][label] = booked_variants_map[cat_id].get(label, 0) + 1
        else:
            variants_map[cat_id][label] = variants_map[cat_id].get(label, 0) + 1

    alerts = []
    for cat_id in candidate_ids:
        m = meta[cat_id]
        variants = [
            {"name": name, "count": cnt}
            for name, cnt in sorted(
                variants_map.get(cat_id, {}).items(),
                key=lambda x: (x[1], x[0].lower()),
            )
        ]
        booked_variants = [
            {"name": name, "count": cnt}
            for name, cnt in sorted(
                booked_variants_map.get(cat_id, {}).items(),
                key=lambda x: (x[1], x[0].lower()),
            )
        ]
        alerts.append(
            {
                "id": cat_id,
                "name": m["name"],
