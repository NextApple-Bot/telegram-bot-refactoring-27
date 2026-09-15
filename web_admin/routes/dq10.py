    real_today = today_local()

    async_session = get_async_session_factory()
    async with async_session() as session:
        snap = await day_snapshot(session, today)
        reconcile = build_day_reconciliation(snap)
        adjustments_detail = await load_adjustments_detail(session, today)

    return templates.TemplateResponse(
        "reconcile.html",
        {
            "request": request,
            "target_date": today.strftime("%d.%m.%Y"),
            "target_date_iso": today.isoformat(),
            "yesterday_iso": yesterday.isoformat(),
            "tomorrow_iso": tomorrow.isoformat(),
            "real_today_iso": real_today.isoformat(),
            "is_today": today == real_today,
            "reconcile": reconcile,
            "adjustments_detail": adjustments_detail,
        },
    )


@router.post("/toggle_seller_day")
async def toggle_seller_day(
    seller_id: int = Form(...), target_date: str = Form(...)
):
    try:
        date_obj = datetime.strptime(target_date[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "Неверная дата"}, status_code=400)

    async_session = get_async_session_factory()
