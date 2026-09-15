            {"success": False, "error": "target_date is required"},
            status_code=400,
        )

    try:
        target_date = datetime.strptime(str(target_date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse(
            {"success": False, "error": f"Неверная дата: {target_date_str}"},
            status_code=400,
        )

    reason = (data.get("reason") or "").strip() or None

    def _num(key: str) -> float:
        return _parse_number(data.get(key, 0))

    def _int(key: str) -> int:
        return max(0, int(round(_parse_number(data.get(key, 0)))))

    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            raw_sales = await raw_sales_count(session, target_date)
            raw_pre = await raw_preorders_count(session, target_date)
            raw_book = await raw_bookings_count(session, target_date)
            raw_pay = await raw_payments(session, target_date)
            from web_admin.services.day_stats import (
                raw_accessories_count,
                raw_accessories_revenue,
            )
            raw_acc = await raw_accessories_count(session, target_date)
            raw_acc_rev = await raw_accessories_revenue(session, target_date)

            targets = {
                "sales_count": float(_int("sales_count")),
                "preorders_count": float(_int("preorders_count")),
