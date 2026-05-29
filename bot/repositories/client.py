import json
import logging
from datetime import datetime

from sqlalchemy import func, select

from bot.db import get_async_session_factory
from bot.models import Client, Purchase

logger = logging.getLogger(__name__)


class ClientRepository:
    """Репозиторий для работы с клиентами и покупками (SQLAlchemy 2.0)."""

    @staticmethod
    async def get_or_create_client(
        phone: str | None = None,
        phones: list[str] | None = None,
        full_name: str | None = None,
        telegram_username: str | None = None,
        social_network: str | None = None,
        referral_source: str | None = None,
        birth_date: str | None = None,
        conn=None
    ) -> int:
        async def _impl(session):
            if phone:
                result = await session.execute(
                    select(Client).where(Client.phone == phone)
                )
                client = result.scalar_one_or_none()
                if client:
                    if full_name and full_name != client.full_name:
                        client.full_name = full_name
                    if telegram_username and telegram_username != client.telegram_username:
                        client.telegram_username = telegram_username
                    if social_network and social_network != client.social_network:
                        client.social_network = social_network
                    if referral_source and referral_source != client.referral_source:
                        client.referral_source = referral_source
                    if phones:
                        existing_phones = set(client.phones.split(',')) if client.phones else set()
                        existing_phones.update(phones)
                        new_phones_str = ",".join(sorted(existing_phones))
                        if new_phones_str != client.phones:
                            client.phones = new_phones_str
                    if birth_date is not None and birth_date != client.birth_date:
                        client.birth_date = birth_date
                    client.updated_at = datetime.now()
                    logger.info(f"✅ Клиент {client.id} обновлён")
                    return client.id
                else:
                    phones_str = ",".join(sorted(set(phones))) if phones else None
                    new_client = Client(
                        full_name=full_name,
                        phone=phone,
                        phones=phones_str,
                        telegram_username=telegram_username,
                        social_network=social_network,
                        referral_source=referral_source,
                        birth_date=birth_date
                    )
                    session.add(new_client)
                    await session.flush()
                    logger.info(f"✅ Клиент {new_client.id} создан")
                    return new_client.id
            else:
                phones_str = ",".join(sorted(set(phones))) if phones else None
                new_client = Client(
                    full_name=full_name,
                    phones=phones_str,
                    telegram_username=telegram_username,
                    social_network=social_network,
                    referral_source=referral_source,
                    birth_date=birth_date
                )
                session.add(new_client)
                await session.flush()
                return new_client.id

        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                return await _impl(session)

    @staticmethod
    async def add_purchase(
        client_id: int,
        items: list,
        total_amount: float,
        payment_details: dict,
        purchase_type: str = 'sale',
        conn=None
    ):
        items_json = json.dumps(items, ensure_ascii=False)
        payment_json = json.dumps(payment_details, ensure_ascii=False)

        async def _impl(session):
            new_purchase = Purchase(
                client_id=client_id,
                items_json=items_json,
                total_amount=total_amount,
                payment_details=payment_json,
                purchase_type=purchase_type
            )
            session.add(new_purchase)

        if conn is not None:
            await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                await _impl(session)

    @staticmethod
    async def get_client_purchases(client_id: int) -> list[dict]:
        async_session = get_async_session_factory()
        async with async_session() as session:
            result = await session.execute(
                select(Purchase).where(Purchase.client_id == client_id).order_by(Purchase.created_at.desc())
            )
            purchases = result.scalars().all()
            return [
                {
                    "id": p.id,
                    "client_id": p.client_id,
                    "items_json": p.items_json,
                    "total_amount": p.total_amount,
                    "payment_details": p.payment_details,
                    "purchase_type": p.purchase_type,
                    "created_at": p.created_at
                }
                for p in purchases
            ]

    @staticmethod
    async def search_clients(query: str) -> list[dict]:
        async_session = get_async_session_factory()
        async with async_session() as session:
            result = await session.execute(
                select(Client).where(
                    Client.full_name.ilike(f"%{query}%") |
                    Client.phone.ilike(f"%{query}%") |
                    Client.telegram_username.ilike(f"%{query}%")
                ).order_by(Client.updated_at.desc())
            )
            clients = result.scalars().all()
            return [
                {
                    "id": c.id,
                    "full_name": c.full_name,
                    "phone": c.phone,
                    "phones": c.phones,
                    "telegram_username": c.telegram_username,
                    "social_network": c.social_network,
                    "referral_source": c.referral_source,
                    "birth_date": c.birth_date,
                    "created_at": c.created_at,
                    "updated_at": c.updated_at
                }
                for c in clients
            ]

    @staticmethod
    async def get_available_months() -> list[str]:
        async_session = get_async_session_factory()
        async with async_session() as session:
            q1 = select(func.to_char(Client.created_at, 'MM.YYYY')).where(Client.created_at.isnot(None)).distinct()
            res1 = await session.execute(q1)
            months1 = [row[0] for row in res1.all()]
            q2 = select(func.to_char(Purchase.created_at, 'MM.YYYY')).where(Purchase.created_at.isnot(None)).distinct()
            res2 = await session.execute(q2)
            months2 = [row[0] for row in res2.all()]
            return sorted(set(months1 + months2), reverse=True)

    @staticmethod
    async def get_clients_data_for_month(month_str: str) -> list[dict]:
        month, year = map(int, month_str.split('.'))
        start_date = datetime(year, month, 1).date()
        if month == 12:
            end_date = datetime(year + 1, 1, 1).date()
        else:
            end_date = datetime(year, month + 1, 1).date()

        async_session = get_async_session_factory()
        async with async_session() as session:
            q = (
                select(
                    Client.id.label("client_id"),
                    Client.full_name,
                    Client.phone,
                    Client.phones,
                    Client.telegram_username,
                    Client.social_network,
                    Client.referral_source,
                    Client.birth_date,
                    Client.created_at.label("client_created_at"),
                    Purchase.id.label("purchase_id"),
                    Purchase.items_json,
                    Purchase.total_amount,
                    Purchase.payment_details,
                    Purchase.purchase_type,
                    Purchase.created_at.label("purchase_created_at")
                )
                .outerjoin(Purchase, (Client.id == Purchase.client_id) &
                                    (Purchase.created_at >= start_date) &
                                    (Purchase.created_at < end_date))
                .where(
                    (Purchase.id.isnot(None)) |
                    ((Client.created_at >= start_date) & (Client.created_at < end_date))
                )
                .order_by(Client.id, Purchase.created_at)
            )
            result = await session.execute(q)
            rows = result.mappings().all()
            return [
                {
                    "client_id": r["client_id"],
                    "full_name": r["full_name"],
                    "phone": r["phone"],
                    "phones": r["phones"],
                    "telegram_username": r["telegram_username"],
                    "social_network": r["social_network"],
                    "referral_source": r["referral_source"],
                    "birth_date": r["birth_date"],
                    "client_created_at": r["client_created_at"],
                    "purchase_id": r["purchase_id"],
                    "items_json": r["items_json"],
                    "total_amount": r["total_amount"],
                    "payment_details": r["payment_details"],
                    "purchase_type": r["purchase_type"],
                    "purchase_created_at": r["purchase_created_at"],
                }
                for r in rows
            ]
