                session.add(
                    StatsAdjustment(
                        target_date=target_date,
                        metric=metric,
                        base_value=base,
                        target_value=target,
                        delta=delta,
                        reason=reason,
                        updated_at=now_local().replace(tzinfo=None),
                    )
                )
                written += 1

            await session.execute(
                delete(SellerDay).where(SellerDay.date == target_date)
            )
            for sid in seller_ids:
                seller = await session.get(Seller, sid)
                if seller:
                    session.add(SellerDay(seller_id=sid, date=target_date))

            logger.info(
                "close_day %s: adj=%s, sellers=%s",
                target_date, written, seller_ids,
            )

        await log_admin_action(
            "close_day",
            request=request,
            date=str(target_date),
            adjustments=written,
            sellers=len(seller_ids),
        )
        return JSONResponse({
            "success": True,
