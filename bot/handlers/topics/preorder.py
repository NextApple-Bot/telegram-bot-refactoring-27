# Файл: bot/handlers/topics/preorder.py
import logging
import re

from aiogram import F, Router
from aiogram.types import Message

from bot import config
from bot.repositories import ClientRepository, StatsRepository
from bot.services.booking import BookingService
from bot.services.message_service import mark_message_processed, safe_react
from bot.services.payment import PaymentService
from bot.utils.helpers import send_and_clean
from bot.utils.parser import extract_payment_amounts, extract_prepayments, parse_client_data

logger = logging.getLogger(__name__)
router = Router()


@router.message(
    F.chat.id == config.MAIN_GROUP_ID,
    F.message_thread_id == config.THREAD_PREORDER,
    (F.text | F.caption)
)
async def handle_preorder(message: Message):
    content = message.text or message.caption
    if not content:
        return

    is_first_time = await mark_message_processed(message.chat.id, message.message_id)
    if not is_first_time:
        logger.info(f"Сообщение {message.message_id} уже обработано, пропускаем.")
        return

    lines = content.strip().splitlines()
    booking_indices = [i for i, line in enumerate(lines) if re.match(r'^бронь\s*:?$', line.strip().lower())]

    if booking_indices:
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            payments = extract_prepayments('\n'.join(preorder_lines))
            if any(payments.values()):
                try:
                    data = parse_client_data('\n'.join(preorder_lines))
                    if data['phones'] or data['full_name']:
                        await ClientRepository.get_or_create_client(
                            phone=data['main_phone'],
                            phones=data['phones'],
                            full_name=data['full_name'],
                            telegram_username=data['telegram_username'],
                            social_network=data['social_network'],
                            referral_source=data['referral_source']
                        )
                except Exception as e:
                    logger.exception(f"Ошибка при сохранении клиента: {e}")

                await StatsRepository.add_preorder(**payments)
                await PaymentService.add_payments_batch(payments, source_type='preorder')
                await safe_react(message, '👌')

        for idx in booking_indices:
            start = idx + 1
            end = booking_indices[booking_indices.index(idx) + 1] if booking_indices.index(idx) + 1 < len(booking_indices) else len(lines)
            booking_lines = lines[start:end]
            booking_payments = extract_payment_amounts('\n'.join(booking_lines), ignore_prepay=False)
            result = await BookingService.process_booking(booking_lines, booking_payments)
            if not result.get("success"):
                if result.get("reason") == "no_items":
                    await safe_react(message, '‼️')
                    await send_and_clean(
                        bot=message.bot,
                        chat_id=message.chat.id,
                        text="❌ В блоке брони нет товаров с серийными номерами.",
                        reply_to_message_id=message.message_id,
                        message_thread_id=config.THREAD_PREORDER,
                        delete_after=60
                    )
                continue
            await safe_react(message, '👍')
            booked_count = len(result.get("results", []))
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=f"✅ Добавлена бронь на {booked_count} товаров.",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_PREORDER,
                delete_after=60
            )
    else:
        payments = extract_prepayments(content)
        if any(payments.values()):
            try:
                data = parse_client_data(content)
                if data['phones'] or data['full_name']:
                    await ClientRepository.get_or_create_client(
                        phone=data['main_phone'],
                        phones=data['phones'],
                        full_name=data['full_name'],
                        telegram_username=data['telegram_username'],
                        social_network=data['social_network'],
                        referral_source=data['referral_source']
                    )
            except Exception as e:
                logger.exception(f"Ошибка при сохранении клиента: {e}")

            await StatsRepository.add_preorder(**payments)
            await PaymentService.add_payments_batch(payments, source_type='preorder')
            await safe_react(message, '👌')
