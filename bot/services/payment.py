import logging

from bot.db import get_async_session_factory
from bot.models import DailyPayment

logger = logging.getLogger(__name__)


class PaymentService:
    """Централизованное сохранение платежей в daily_payments."""

    @staticmethod
    async def add_payment(payment_type: str, amount: float, source_type: str) -> None:
        if amount <= 0:
            return
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            session.add(DailyPayment(
                type=source_type,
                payment_type=payment_type,
                amount=amount
            ))
            logger.debug(f"Платёж сохранён: {source_type} {payment_type} = {amount}")

    @staticmethod
    async def add_payments_batch(payments: dict, source_type: str) -> None:
        for pay_type, amount in payments.items():
            if amount and amount > 0:
                await PaymentService.add_payment(pay_type, amount, source_type)
