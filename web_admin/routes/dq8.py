        has_adjustments = bool(snap["adjustments"])
        reconcile = build_day_reconciliation(snap)

        low_stock = await _low_stock_alerts(session, LOW_STOCK_THRESHOLD)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "target_date": today.strftime("%d.%m.%Y"),
            "target_date_iso": today.isoformat(),
            "yesterday_iso": yesterday.isoformat(),
            "tomorrow_iso": tomorrow.isoformat(),
            "real_today_iso": real_today.isoformat(),
            "is_today": today == real_today,
            "sales_today": sales_today,
            "revenue_today": total_revenue,
            "sales_change_yesterday": sales_change_yesterday,
            "sales_change_week": sales_change_week,
            "revenue_change_yesterday": revenue_change_yesterday,
            "revenue_change_week": revenue_change_week,
            "payments": payments,
            "total_revenue": total_revenue,
            "plan_amount": 600000,
            "stats": {
                "sales_count": snap["sales_count"],
                "devices_count": snap.get("devices_count", snap["sales_count"]),
