    text = (data.get("text") or "").strip()
    if not text:
        return JSONResponse({"success": False, "error": "Пустой текст"}, status_code=400)
    try:
        from bot.services.payment_parser import extract_payment_amounts, extract_declared_total
        payments = extract_payment_amounts(text)
        declared = None
        try:
            declared = extract_declared_total(text)
        except Exception:
            declared = None
        return JSONResponse({
            "success": True,
            "payments": {k: float(v or 0) for k, v in payments.items()},
            "declared_total": declared,
        })
    except Exception as e:
        logger.exception("parse_payments")
        return JSONResponse({"success": False, "error": str(e)[:300]}, status_code=500)


@router.get("/top_models_data")
async def top_models_data(
    request: Request, days: int = 7, target_date: str | None = None
):
    end_date = (
        datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        if target_date
        else today_local()
    )
    start_date = end_date - timedelta(days=days)

    async_session = get_async_session_factory()
    async with async_session() as session:
