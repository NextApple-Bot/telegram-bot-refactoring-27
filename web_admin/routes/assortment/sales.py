import asyncio
import logging
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from bot.db import get_async_session_factory
from bot.models import DailyPayment, DeletedItem, Item, Sale
from bot.repositories.client import ClientRepository
from bot.services.cache import cache

logger = logging.getLogger(__name__)


def generate_sale_message_id() -> int:
    return uuid.uuid4().int & 0x7FFFFFFFFFFFFFFF


async def handle_sale_from_form(
    item_id: int,
    text: str,
    serial: str,
    category_id: int,
    old_text: str,
    old_serial: str,
    old_category_id: int,
    sale_price: float,
    sale_prepayment: float,
    sale_payment_amount: float,
    sale_payment_type: str,
    sale_platform: str,
    sale_full_name: str,
    sale_phone: str,
    accessories: list = None,
    sale_birth_date: str | None = None,
    sale_bonus: float | None = None,
    sale_bonus_reason: str | None = None,
    sale_change: float | None = None,
    sale_change_type: str | None = None,
    conn=None
):
    try:
        if not sale_price:
            raise ValueError("Укажите стоимость продажи")
        if sale_payment_type != "paid" and (not sale_payment_amount or sale_payment_amount <= 0):
            raise ValueError("Укажите сумму оплаты")
        if not sale_payment_type:
            sale_payment_type = "cash"

        sale_message_id = generate_sale_message_id()

        accessories_total = 0
        processed_accessories = []
        accessories_payments = {}

        own_session = False
        if conn is None:
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True
        else:
            session = conn

        try:
            if own_session:
                await session.begin()

            client_id = None
            phone = sale_phone.strip() if sale_phone else None
            if phone or sale_full_name:
                client_id = await ClientRepository.get_or_create_client(
                    phone=phone,
                    full_name=sale_full_name.strip() if sale_full_name else None,
                    social_network=sale_platform.strip() if sale_platform else None,
                    birth_date=sale_birth_date,
                    conn=session
                )

            if accessories:
                for acc in accessories:
                    acc_price = acc['price']
                    accessories_total += acc_price
                    display_text = acc['name']
                    item_info = None
                    if acc.get('serial'):
                        q = select(Item).where(func.upper(Item.serial) == acc['serial'].strip().upper())
                        item_info = (await session.execute(q)).scalar_one_or_none()
                        if item_info:
                            display_text = item_info.text
                            deleted = DeletedItem(
                                item_id=item_info.id,
                                text=item_info.text,
                                serial=acc['serial'],
                                category_id=item_info.category_id,
                                reason='sale_from_admin',
                                sale_message_id=sale_message_id
                            )
                            session.add(deleted)
                            await session.delete(item_info)

                    processed_accessories.append({
                        "text": display_text,
                        "price": acc_price,
                        "payment_type": acc.get('payment_type')
                    })

                    pay_type = acc.get('payment_type')
                    if pay_type and pay_type != "paid" and acc_price > 0:
                        accessories_payments[pay_type] = accessories_payments.get(pay_type, 0) + acc_price

            all_payments = dict(accessories_payments)
            if sale_payment_type != "paid" and sale_payment_amount > 0:
                all_payments[sale_payment_type] = all_payments.get(sale_payment_type, 0) + sale_payment_amount

            for pay_type, amount in all_payments.items():
                if amount > 0:
                    payment = DailyPayment(
                        type='sale',
                        payment_type=pay_type,
                        amount=amount,
                        sale_message_id=sale_message_id
                    )
                    session.add(payment)

            if client_id:
                items_list = [{"item_text": text, "price": sale_price, "serial": serial}]
                if processed_accessories:
                    for acc in processed_accessories:
                        items_list.append({"item_text": acc['text'], "price": acc['price']})
                payment_details_json = {pt: amt for pt, amt in all_payments.items() if amt > 0}
                await ClientRepository.add_purchase(
                    client_id=client_id,
                    items=items_list,
                    total_amount=sale_price + accessories_total,
                    payment_details=payment_details_json,
                    purchase_type='sale',
                    conn=session
                )

            old_item = await session.get(Item, item_id)
            if old_item:
                deleted = DeletedItem(
                    item_id=old_item.id,
                    text=old_text,
                    serial=old_serial,
                    category_id=old_category_id,
                    reason='sale_from_admin',
                    sale_message_id=sale_message_id
                )
                session.add(deleted)
                await session.delete(old_item)

            sale = Sale(
                count=1,
                cash=0,
                terminal=0,
                qr=0,
                transfer=0,
                invoice=0,
                installment=0,
                is_accessory=False,
                message_id=sale_message_id
            )
            session.add(sale)

            if own_session:
                await session.commit()

            from .notifications import send_sale_notification
            asyncio.create_task(send_sale_notification(
                item_text=text,
                price=sale_price,
                payment_type=sale_payment_type,
                prepayment=sale_prepayment if sale_prepayment and sale_prepayment > 0 else None,
                payment_amount=sale_payment_amount if sale_payment_type != "paid" else None,
                platform=sale_platform,
                full_name=sale_full_name,
                phone=sale_phone,
                birth_date=sale_birth_date,
                bonus=sale_bonus,
                bonus_reason=sale_bonus_reason,
                change=sale_change,
                change_type=sale_change_type,
                accessories=processed_accessories,
                accessories_total=accessories_total
            ))

        except ValueError as e:
            logger.warning(f"Некорректные данные продажи: {e}")
            if own_session:
                await session.rollback()
            return {"error": str(e)}
        except SQLAlchemyError:
            logger.exception("Ошибка БД при продаже")
            if own_session:
                await session.rollback()
            return {"error": "Ошибка базы данных"}
        finally:
            if own_session:
                await session.close()

        await cache.delete(f"dashboard:summary:{date.today().isoformat()}")
        return {"success": True}
    except Exception as e:
        logger.exception("Неожиданная ошибка в handle_sale_from_form")
        return {"error": str(e)}
