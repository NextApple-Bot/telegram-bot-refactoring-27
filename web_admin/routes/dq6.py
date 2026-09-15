        revenue_today = snap["total_revenue"]

        sales_change_yesterday = calculate_change(sales_today, snap_y["sales_count"])
        sales_change_week = calculate_change(sales_today, snap_w["sales_count"])
        revenue_change_yesterday = calculate_change(
            float(revenue_today), float(snap_y["total_revenue"])
        )
        revenue_change_week = calculate_change(
            float(revenue_today), float(snap_w["total_revenue"])
        )

        payments = snap["payments"]
        total_revenue = snap["total_revenue"]

        active_bookings = (
            await session.execute(
                select(func.count(Item.id)).where(Item.is_booked.is_(True))
            )
        ).scalar() or 0

        chart_dates, chart_sales, chart_revenue = [], [], []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            s = await day_snapshot(session, d)
            chart_dates.append(d.strftime("%d.%m"))
            chart_sales.append(s["sales_count"])
            chart_revenue.append(float(s["total_revenue"]))

        sellers_rows = (
            await session.execute(
