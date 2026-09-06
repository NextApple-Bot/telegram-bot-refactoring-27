import logging
from datetime import date

from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import Booking, DailyPayment, Preorder, Sale

logger = logging.getLogger(__name__)


class StatsRepository:
    """Репозиторий для работы со статистикой (SQLAlchemy 2.0)."""

    @staticmethod
    async def add_sale(
        item_id: int = None,
        count: int = 1,
        cash: float = 0,
        terminal: float = 0,
        qr: float = 0,
        transfer: float = 0,
        invoice: float = 0,
        installment: float = 0,
        is_accessory: bool = False,
        message_id: int = None,
        conn=None
    ):
        async def _impl(session):
            sale = Sale(
                item_id=item_id,
                count=count,
                cash=cash,
                terminal=terminal,
                qr=qr,
                transfer=transfer,
                invoice=invoice,
                installment=installment,
                is_accessory=is_accessory,
                message_id=message_id
            )
            session.add(sale)
            try:
                await session.flush()
            except Exception:
                await session.rollback()
                logger.warning(f"Продажа с message_id={message_id} уже существует, пропущено")

        if conn is not None:
            await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                await _impl(session)

    @staticmethod
    async def add_preorder(cash=0, terminal=0, qr=0, transfer=0, invoice=0, installment=0):
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            preorder = Preorder(
                cash=cash,
                terminal=terminal,
                qr=qr,
                transfer=transfer,
                invoice=invoice,
                installment=installment
            )
            session.add(preorder)

    @staticmethod
    async def add_booking(item_id: int, total_amount: float):
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            booking = Booking(
                item_id=item_id,
                total_amount=total_amount
            )
            session.add(booking)

    @staticmethod
    async def get_today_stats() -> dict:
        today = date.today()
        async_session = get_async_session_factory()
        async with async_session() as session:
            # Продажи (устройства + аксессуары)
            sale_sums = await session.execute(
                select(
                    func.coalesce(func.sum(Sale.cash), 0).label("cash"),
                    func.coalesce(func.sum(Sale.terminal), 0).label("terminal"),
                    func.coalesce(func.sum(Sale.qr), 0).label("qr"),
                    func.coalesce(func.sum(Sale.transfer), 0).label("transfer"),
                    func.coalesce(func.sum(Sale.invoice), 0).label("invoice"),
                    func.coalesce(func.sum(Sale.installment), 0).label("installment"),
                    func.count(Sale.id).label("sales_count"),
                    func.coalesce(
                        func.sum(Sale.count).filter(Sale.is_accessory.is_(True)), 0
                    ).label("accessories_count"),
                    func.coalesce(
                        func.sum(Sale.count).filter(
                            (Sale.is_accessory.is_(False)) | (Sale.is_accessory.is_(None))
                        ),
                        0,
                    ).label("devices_count"),
                ).where(func.date(Sale.sold_at) == today)
            )
            sale_row = sale_sums.mappings().one()

            # Предзаказы
            pre_sums = await session.execute(
                select(
                    func.coalesce(func.sum(Preorder.cash), 0).label("cash"),
                    func.coalesce(func.sum(Preorder.terminal), 0).label("terminal"),
                    func.coalesce(func.sum(Preorder.qr), 0).label("qr"),
                    func.coalesce(func.sum(Preorder.transfer), 0).label("transfer"),
                    func.coalesce(func.sum(Preorder.invoice), 0).label("invoice"),
                    func.coalesce(func.sum(Preorder.installment), 0).label("installment"),
                    func.count(Preorder.id).label("preorders_count")
                ).where(func.date(Preorder.created_at) == today)
            )
            pre_row = pre_sums.mappings().one()

            # Брони
            book_sums = await session.execute(
                select(
                    func.coalesce(func.sum(Booking.total_amount), 0).label("total"),
                    func.count(Booking.id).label("bookings_count")
                ).where(func.date(Booking.booked_at) == today)
            )
            book_row = book_sums.mappings().one()

            accessories_count = int(sale_row["accessories_count"] or 0)
            devices_count = int(sale_row["devices_count"] or 0)
            # если старые записи без флага — devices ≈ total - accessories
            total_sales = int(sale_row["sales_count"] or 0)
            if devices_count == 0 and accessories_count == 0 and total_sales > 0:
                devices_count = total_sales

            return {
                'date': today.strftime('%d.%m.%y'),
                'preorders_count': pre_row['preorders_count'],
                'bookings_count': book_row['bookings_count'],
                'sales_count': total_sales,
                'devices_count': devices_count,
                'accessories_count': accessories_count,
                'preorders': {
                    'cash': pre_row['cash'],
                    'terminal': pre_row['terminal'],
                    'qr': pre_row['qr'],
                    'transfer': pre_row['transfer'],
                    'invoice': pre_row['invoice'],
                    'installment': pre_row['installment'],
                },
                'sales': {
                    'cash': sale_row['cash'],
                    'terminal': sale_row['terminal'],
                    'qr': sale_row['qr'],
                    'transfer': sale_row['transfer'],
                    'invoice': sale_row['invoice'],
                    'installment': sale_row['installment'],
                },
                'bookings_total': book_row['total'],
            }

    @staticmethod
    async def reset_today_stats():
        today = date.today()
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            # Продажи
            sales = await session.execute(
                select(Sale).where(func.date(Sale.sold_at) == today)
            )
            for s in sales.scalars():
                await session.delete(s)

            # Предзаказы
            preorders = await session.execute(
                select(Preorder).where(func.date(Preorder.created_at) == today)
            )
            for p in preorders.scalars():
                await session.delete(p)

            # Брони
            bookings = await session.execute(
                select(Booking).where(func.date(Booking.booked_at) == today)
            )
            for b in bookings.scalars():
                await session.delete(b)

            # Платежи
            payments = await session.execute(
                select(DailyPayment).where(func.date(DailyPayment.created_at) == today)
            )
            for dp in payments.scalars():
                await session.delete(dp)
