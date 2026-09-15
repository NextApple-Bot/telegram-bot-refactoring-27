        return JSONResponse({"success": False, "error": f"Некорректный JSON: {e}"}, status_code=400)

    target_date_str = data.get("target_date")
    if not target_date_str:
        return JSONResponse({"success": False, "error": "target_date is required"}, status_code=400)
    try:
        target_date = datetime.strptime(str(target_date_str)[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверная дата"}, status_code=400)

    reason = (data.get("reason") or "").strip() or "закрытие дня"
    seller_ids_raw = data.get("seller_ids") or []
    try:
        seller_ids = sorted({int(x) for x in seller_ids_raw})
    except (TypeError, ValueError):
        return JSONResponse({"success": False, "error": "seller_ids must be int list"}, status_code=400)

    def _num(key: str) -> float:
        return _parse_number(data.get(key, 0))

    def _int(key: str) -> int:
        return max(0, int(round(_parse_number(data.get(key, 0)))))

    try:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            raw_sales = await raw_sales_count(session, target_date)
