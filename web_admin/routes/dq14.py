                        updated_at=now_local().replace(tzinfo=None),
                    )
                )
                written += 1

            logger.info(
                "Корректировки за %s: %s метрик (Sale/платежи не трогали)",
                target_date,
                written,
            )

        await log_admin_action(
            "update_stats",
            request=request,
            date=str(target_date),
            reason=reason,
        )
        return JSONResponse(
            {
                "success": True,
                "mode": "adjustment",
                "target_date": target_date.isoformat(),
                "message": "Сохранено как корректировка. Реальные продажи не удалялись.",
            }
        )

    except Exception as e:
        logger.exception("Ошибка update_stats за %s", target_date_str)
        return JSONResponse(
            {"success": False, "error": str(e)[:500]},
            status_code=500,
        )


@router.post("/close_day")
async def close_day(request: Request):
    try:
        data = await request.json()
    except Exception as e:
