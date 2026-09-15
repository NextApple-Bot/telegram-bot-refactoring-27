def _is_low_stock_family(category_name: str) -> bool:
    n = (category_name or "").strip().lower().rstrip(":")
    if not n or n in SKIP_CATEGORY_NAMES:
        return False
    for fam in LOW_STOCK_FAMILIES:
        if n == fam or n.startswith(fam + " ") or n.startswith(fam):
            return True
    return False


def _variant_label(text: str | None, serial: str | None = None) -> str:
    t = (text or "").strip()
    if not t:
        return "—"
    t = _BOOKING_MARK.sub(" ", t)
    t = _SERIAL_PARENS.sub(" ", t)
    if serial:
        t = re.sub(re.escape(serial), " ", t, flags=re.IGNORECASE)
    t = re.sub(r"\s+", " ", t).strip(" ,.;")
    t = re.sub(r"\(\s*\)", "", t)
    t = re.sub(r"[)\]]+$", "", t).strip(" ,.;")
    t = re.sub(r"\s+", " ", t).strip(" ,.;")
    return t or (text or "—").strip()


async def _low_stock_alerts(session, threshold: int) -> list[dict]:
    free_q = (
        select(
            Category.id,
            Category.name,
            func.count(Item.id).label("free_count"),
        )
        .select_from(Category)
        .outerjoin(
            Item,
            (Item.category_id == Category.id) & (Item.is_booked.is_(False)),
        )
