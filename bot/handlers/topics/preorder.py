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
    """
    Обработчик сообщений в топике «Предзаказы».
    Поддерживает два сценария:
    1. Обычный предзаказ (предоплата).
    2. Смешанный формат: предзаказ + блок(и) брони.
    """
    content = message.text or message.caption
    if not content:
        return

    # Защита от повторной обработки
    is_first_time = await mark_message_processed(message.chat.id, message.message_id)
    if not is_first_time:
        logger.info(f"Сообщение {message.message_id} уже обработано, пропускаем.")
        return

    lines = content.strip().splitlines()
    booking_indices = [
        i for i, line in enumerate(lines)
        if re.match(r'^бронь\s*:?$', line.strip().lower())
    ]

    if booking_indices:
        # === Сценарий: есть блоки брони ===
        # Обрабатываем предзаказы, которые идут ДО первого блока "бронь"
        preorder_lines = lines[:booking_indices[0]]
        if preorder_lines:
            payments = extract_prepayments('\n'.join(preorder_lines))
            if any(payments.values()):
                try:
                    data = parse_client_data('\n'.join(preorder_lines))
                    if data.get('phones') or data.get('full_name'):
                        await ClientRepository.get_or_create_client(
                            phone=data.get('main_phone'),
                            phones=data.get('phones'),
                            full_name=data.get('full_name'),
                            telegram_username=data.get('telegram_username'),
                            social_network=data.get('social_network'),
                            referral_source=data.get('referral_source')
                        )
                except Exception as e:
                    logger.exception(f"Ошибка при сохранении клиента (предзаказ): {e}")

                await StatsRepository.add_preorder(**payments)
                await PaymentService.add_payments_batch(payments, source_type='preorder')
                await safe_react(message, '👌')
                logger.info(f"Предзаказ обработан: {payments}")

        # Обрабатываем каждый блок брони
        for i, start_idx in enumerate(booking_indices):
            start = start_idx + 1
            # Определяем конец текущего блока брони
            if i + 1 < len(booking_indices):
                end = booking_indices[i + 1]
            else:
                end = len(lines)

            booking_lines = lines[start:end]
            if not booking_lines:
                continue

            booking_payments = extract_payment_amounts('\n'.join(booking_lines), ignore_prepay=False)

            try:
                result = await BookingService.process_booking(booking_lines, booking_payments)
            except Exception as e:
                logger.exception(f"Ошибка при обработке блока брони: {e}")
                await safe_react(message, '‼️')
                continue

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
                logger.warning(f"Блок брони не обработан: {result}")
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
            logger.info(f"Бронь успешно обработана: {booked_count} товаров")

    else:
        # === Обычный предзаказ без блоков брони ===
        payments = extract_prepayments(content)
        if any(payments.values()):
            try:
                data = parse_client_data(content)
                if data.get('phones') or data.get('full_name'):
                    await ClientRepository.get_or_create_client(
                        phone=data.get('main_phone'),
                        phones=data.get('phones'),
                        full_name=data.get('full_name'),
                        telegram_username=data.get('telegram_username'),
                        social_network=data.get('social_network'),
                        referral_source=data.get('referral_source')
                    )
            except Exception as e:
                logger.exception(f"Ошибка при сохранении клиента (предзаказ): {e}")

            await StatsRepository.add_preorder(**payments)
            await PaymentService.add_payments_batch(payments, source_type='preorder')
            await safe_react(message, '👌')
            logger.info(f"Предзаказ обработан: {payments}")
        else:
            logger.info(f"Сообщение {message.message_id} не содержит предоплат — пропущено.")
