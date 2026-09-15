                "bookings_count": float(_int("bookings_count")),
            }
            for pt in PAYMENT_METRICS:
                targets[pt] = max(0.0, _num(pt))

            bases = {
                "sales_count": float(raw_sales),
                "preorders_count": float(raw_pre),
                "bookings_count": float(raw_book),
                **{k: float(raw_pay.get(k, 0)) for k in PAYMENT_METRICS},
            }

            await session.execute(
                delete(StatsAdjustment).where(
                    StatsAdjustment.target_date == target_date
                )
            )

            written = 0
            for metric in ALL_METRICS:
                base = bases.get(metric, 0.0)
                target = targets.get(metric, 0.0)
                delta = target - base
                if abs(delta) < 1e-9:
                    continue
                session.add(
                    StatsAdjustment(
                        target_date=target_date,
                        metric=metric,
                        base_value=base,
                        target_value=target,
                        delta=delta,
                        reason=reason,
