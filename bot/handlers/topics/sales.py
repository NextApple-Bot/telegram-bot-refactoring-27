# Файл: bot/handlers/topics/sales.py
import logging
import re

from aiogram import F, Router
from aiogram.types import Message

from bot import config
from bot.repositories import ClientRepository
from bot.services.message_service import mark_message_processed, safe_react
from bot.services.payment import PaymentService
from bot.services.sale import SaleService
from bot.utils.helpers import send_and_clean
from bot.utils.parser import extract_payment_amounts, parse_client_data

logger = logging.getLogger(__name__)
router = Router()

TRADE_IN_PATTERNS = [
    r'trade\s*in',
    r'трейд\s*ин',
    r'trade\-in',
]


def remove_trade_in_lines(text: str) -> str:
    lines = text.splitlines()
    filtered = []
    for line in lines:
        if any(re.search(p, line, re.IGNORECASE) for p in TRADE_IN_PATTERNS):
            continue
        filtered.append(line)
    return '\n'.join(filtered)


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_SALES,
    (F.text | F.caption)
)
async def handle_sales_message(message: Message):
    content = message.text or message.caption
    if not content:
        return

    is_first_time = await mark_message_processed(message.chat.id, message.message_id)
    if not is_first_time:
        logger.info(f"Сообщение {message.message_id} уже обработано, пропускаем.")
        return

    content = remove_trade_in_lines(content)
    payments = extract_payment_amounts(content, ignore_prepay=True)
    result = await SaleService.process_sale(content, message.chat.id, message.message_id, payments)

    if result.get("skipped"):
        logger.info(f"Сообщение {message.message_id} было пропущено.")
        return

    try:
        data = parse_client_data(content)
        if data['phones'] or data['full_name']:
            await ClientRepository.get_or_create_client(
                phone=data['main_phone'],
                phones=data['phones'],
                full_name=data['full_name'],
                telegram_username=data['telegram_username'],
                social_network=data['social_network'],
                referral_source=data['referral_source'],
                birth_date=data.get('birth_date')
            )
    except Exception as e:
        logger.exception(f"Ошибка при сохранении клиента: {e}")

    if not result.get("skip_payments", False):
        await PaymentService.add_payments_batch(payments, source_type='sale')
        logger.info(f"💰 Платежи сохранены: {payments}")

    if result.get("is_accessory"):
        await safe_react(message, '⚡️')
        logger.info("Аксессуар: платежи сохранены, статистика продаж не изменена.")
    elif result.get("sold_items"):
        await safe_react(message, '🔥')
        logger.info(f"✅ Продажа: {len(result['sold_items'])} товаров, статистика и платежи сохранены.")
    elif result.get("not_found"):
        await safe_react(message, '‼️')
        text = "❌ Серийные номера не найдены в ассортименте:\n" + "\n".join(result["not_found"])
        await send_and_clean(
            bot=message.bot,
            chat_id=message.chat.id,
            text=text,
            reply_to_message_id=message.message_id,
            message_thread_id=config.THREAD_SALES,
            delete_after=60
        )
        logger.info("Серийные номера не найдены – ничего не сохранено.")
    else:
        logger.info("Сообщение уже обработано или нет действий.")
