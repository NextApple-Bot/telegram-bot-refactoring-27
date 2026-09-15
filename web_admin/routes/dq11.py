    async with async_session() as session, session.begin():
        existing = (
            await session.execute(
                select(SellerDay).where(
                    SellerDay.seller_id == seller_id, SellerDay.date == date_obj
                )
            )
        ).scalar_one_or_none()

        if existing:
            await session.delete(existing)
            status = "removed"
        else:
            session.add(SellerDay(seller_id=seller_id, date=date_obj))
            status = "added"

    return {"success": True, "status": status}


@router.post("/update_stats")
async def update_stats(request: Request):
    logger.info(
        "update_stats: method=%s path=%s auth=%s",
        request.method,
        request.url.path,
        bool(request.session.get("authenticated")),
    )

    try:
        data = await request.json()
    except Exception as e:
        logger.warning("update_stats: bad JSON: %s", e)
        return JSONResponse(
            {"success": False, "error": "Некорректный JSON"},
            status_code=400,
        )

    target_date_str = data.get("target_date")
    if not target_date_str:
        return JSONResponse(
