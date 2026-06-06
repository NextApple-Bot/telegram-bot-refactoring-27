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

# Паттерны для удаления строк с Trade-in (чтобы не мешали парсингу)
TRADE_IN_PATTERNS = [
    r'trade\s*in',
    r'трейд\s*ин',
    r'trade\-in',
]


def remove_trade_in_lines(text: str) -> str:
    """Удаляет строки, содержащие упоминание Trade-in."""
    lines = text.splitlines()
    filtered = [
        line for line in lines
        if not any(re.search(p, line, re.IGNORECASE) for p in TRADE_IN_PATTERNS)
    ]
    return '\n'.join(filtered)


@router.message(
    F.message_thread_id == config.THREAD_SALES,
    (F.text | F.caption)
)
async def handle_sales_message(message: Message) -> None:
    """
    Обработчик сообщений о продажах в соответствующем топике.
    """
    content = message.text or message.caption
    if not content:
        return

    # === Защита от повторной обработки ===
    is_first_time = await mark_message_processed(message.chat.id, message.message_id)
    if not is_first_time:
        logger.debug(f"Сообщение {message.message_id} уже обработано — пропускаем")
        return

    # Удаляем строки с Trade-in
    content = remove_trade_in_lines(content)

    # Извлекаем платежи (игнорируем предоплату)
    payments = extract_payment_amounts(content, ignore_prepay=True)

    # === Основная обработка продажи ===
    result = await SaleService.process_sale(
        content=content,
        chat_id=message.chat.id,
        message_id=message.message_id,
        payments=payments
    )

    if result.get("skipped"):
        logger.info(f"Продажа пропущена (message_id={message.message_id})")
        return

    # === Сохранение клиента (если есть данные) ===
    try:
        data = parse_client_data(content)
        if data.get('phones') or data.get('full_name'):
            await ClientRepository.get_or_create_client(
                phone=data.get('main_phone'),
                phones=data.get('phones'),
                full_name=data.get('full_name'),
                telegram_username=data.get('telegram_username'),
                social_network=data.get('social_network'),
                referral_source=data.get('referral_source'),
                birth_date=data.get('birth_date')
            )
    except Exception as e:
        logger.exception(f"Ошибка при сохранении/обновлении клиента: {e}")

    # === Сохранение платежей ===
    if not result.get("skip_payments", False):
        await PaymentService.add_payments_batch(payments, source_type='sale')
        logger.info(f"💰 Платежи сохранены: {payments}")

    # === Реакция и логирование результата ===
    if result.get("is_accessory"):
        await safe_react(message, '⚡️')
        logger.info(f"Аксессуар обработан (message_id={message.message_id})")

    elif result.get("sold_items"):
        await safe_react(message, '🔥')
        logger.info(
            f"✅ Продажа успешно обработана: {len(result['sold_items'])} товаров "
            f"(message_id={message.message_id})"
        )

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
        logger.warning(f"Серийные номера не найдены (message_id={message.message_id})")

    else:
        logger.info(f"Сообщение обработано без дополнительных действий (message_id={message.message_id})")
