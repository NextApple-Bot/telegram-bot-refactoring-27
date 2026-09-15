            "target_date": target_date.isoformat(),
            "adjustments": written,
            "sellers": len(seller_ids),
            "message": "День закрыт: цифры и смены сохранены.",
        })
    except Exception as e:
        logger.exception("close_day error")
        return JSONResponse({"success": False, "error": str(e)[:500]}, status_code=500)


@router.get("/adjustments")
async def list_adjustments(target_date: str):
    try:
        day = datetime.strptime(str(target_date)[:10], "%Y-%m-%d").date()
    except ValueError:
        return JSONResponse({"success": False, "error": "bad date"}, status_code=400)
    async_session = get_async_session_factory()
    async with async_session() as session:
        rows = await load_adjustments_detail(session, day)
    return JSONResponse({"success": True, "target_date": day.isoformat(), "items": rows})



@router.post("/parse_payments")
async def parse_payments(request: Request):
    """Разбор текста итогов дня → суммы по способам оплаты (для UI дашборда)."""
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"success": False, "error": "Некорректный JSON"}, status_code=400)
