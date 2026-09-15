                "free": m["free"],
                "booked": m["booked"],
                "total": m["total"],
                "level": m["level"],
                "variants": variants,
                "booked_variants": booked_variants,
            }
        )
    return alerts


@router.get("/")
async def dashboard(request: Request, target_date: str | None = None):
    try:
        today = (
            today_local()
            if not target_date
            else datetime.strptime(target_date[:10], "%Y-%m-%d").date()
        )
    except ValueError:
        today = today_local()

    yesterday = today - timedelta(days=1)
    tomorrow = today + timedelta(days=1)
    week_ago = today - timedelta(days=7)
    real_today = today_local()

    async_session = get_async_session_factory()
    async with async_session() as session:
        async with session.begin():
            await _ensure_default_sellers(session)

        snap = await day_snapshot(session, today)
        snap_y = await day_snapshot(session, yesterday)
        snap_w = await day_snapshot(session, week_ago)
        month = await month_totals(session, today)

        sales_today = snap["sales_count"]
