from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db import get_async_session_factory
from bot.models import Client, Purchase


class ClientRepository:
    """Репозиторий для работы с клиентами и покупками."""

    @staticmethod
    async def find_by_phone_or_name(query: str) -> Optional[Client]:
        async with get_async_session_factory()() as session:
            stmt = select(Client).where(
                (Client.phone.ilike(f"%{query}%")) | (Client.full_name.ilike(f"%{query}%"))
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    @staticmethod
    async def get_all_clients_for_export() -> List[Client]:
        async with get_async_session_factory()() as session:
            stmt = select(Client).order_by(Client.created_at.desc())
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_all_purchases_for_export() -> List[Purchase]:
        async with get_async_session_factory()() as session:
            stmt = (
                select(Purchase)
                .join(Client)
                .order_by(Purchase.created_at.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    @staticmethod
    async def get_full_report() -> List[dict]:
        async with get_async_session_factory()() as session:
            stmt = """
                SELECT 
                    c.full_name as client_name,
                    c.phone,
                    p.id as purchase_id,
                    p.created_at,
                    p.total_amount,
                    p.items_json
                FROM purchases p
                JOIN clients c ON p.client_id = c.id
                ORDER BY p.created_at DESC
            """
            result = await session.execute(stmt)
            return [dict(row) for row in result.mappings().all()]

    @staticmethod
    async def get_clients_data_for_month(month: str) -> List[dict]:
        """month в формате YYYY-MM"""
        async with get_async_session_factory()() as session:
            stmt = """
                SELECT 
                    c.id as client_id,
                    c.full_name,
                    c.phone,
                    c.telegram_username,
                    c.social_network,
                    c.referral_source,
                    c.created_at as client_created_at,
                    p.id as purchase_id,
                    p.created_at as purchase_created_at,
                    p.total_amount,
                    p.payment_details,
                    p.purchase_type,
                    p.items_json
                FROM clients c
                LEFT JOIN purchases p ON p.client_id = c.id
                WHERE to_char(c.created_at, 'YYYY-MM') = :month 
                   OR to_char(p.created_at, 'YYYY-MM') = :month
                ORDER BY c.created_at DESC, p.created_at DESC
            """
            result = await session.execute(stmt, {"month": month})
            return [dict(row) for row in result.mappings().all()]
