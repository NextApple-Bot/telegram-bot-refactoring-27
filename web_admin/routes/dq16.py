            raw_pre = await raw_preorders_count(session, target_date)
            raw_book = await raw_bookings_count(session, target_date)
            raw_pay = await raw_payments(session, target_date)
            from web_admin.services.day_stats import (
                raw_accessories_count,
                raw_accessories_revenue,
            )
            raw_acc = await raw_accessories_count(session, target_date)
            raw_acc_rev = await raw_accessories_revenue(session, target_date)

            targets = {
                "sales_count": float(_int("sales_count")),
                "preorders_count": float(_int("preorders_count")),
                "bookings_count": float(_int("bookings_count")),
                "accessories_count": float(_int("accessories_count")),
                "accessories_revenue": max(0.0, _num("accessories_revenue")),
            }
            for pt in PAYMENT_METRICS:
                targets[pt] = max(0.0, _num(pt))

            bases = {
                "sales_count": float(raw_sales),
                "preorders_count": float(raw_pre),
                "bookings_count": float(raw_book),
                "accessories_count": float(raw_acc),
                "accessories_revenue": float(raw_acc_rev),
                **{k: float(raw_pay.get(k, 0)) for k in PAYMENT_METRICS},
            }

            await session.execute(
                delete(StatsAdjustment).where(StatsAdjustment.target_date == target_date)
            )
            written = 0
            for metric in ALL_METRICS:
                base = bases.get(metric, 0.0)
                target = targets.get(metric, 0.0)
                delta = target - base
                if abs(delta) < 1e-9:
                    continue
