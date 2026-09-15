                "accessories_count": snap.get("accessories_count", 0),
                "preorders_count": snap["preorders_count"],
                "bookings_count": snap["bookings_count"],
                "active_bookings": active_bookings,
            },
            "has_adjustments": has_adjustments,
            "reconcile": reconcile,
            "sellers": sellers,
            "chart_dates": chart_dates,
            "chart_sales": chart_sales,
            "chart_revenue": chart_revenue,
            "top_labels": top_labels,
            "top_counts": top_counts,
            "top_models": top_models_list,
            "days": 7,
            "low_stock": low_stock,
            "low_stock_threshold": LOW_STOCK_THRESHOLD,
            "month": month,
        },
    )


@router.get("/reconcile")
async def reconcile_day(request: Request, target_date: str | None = None):
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
