import logging
import re

from aiogram import F, Router
from aiogram.types import Message

from bot import config
from bot.handlers.topics.filters import in_main_group, in_preorder
from bot.repositories import ClientRepository, StatsRepository
from bot.services.booking import BookingService
from bot.services.message_service import mark_message_processed, safe_react
from bot.services.payment import PaymentService
from bot.utils.helpers import send_and_clean
from bot.utils.parser import extract_payment_amounts, extract_prepayments, parse_client_data

logger = logging.getLogger(__name__)
router = Router()


def _thread_preorder() -> int:
    try:
        return int(config.THREAD_PREORDER)
    except (TypeError, ValueError):
        return 0


def _booking_payments_from_block(booking_lines: list[str]) -> dict[str, float]:
    """П/О из блока брони: сначала строки предоплаты, иначе все оплаты."""
    text = "\n".join(booking_lines)
    payments = extract_prepayments(text)
    if any(float(v or 0) > 0 for v in payments.values()):
        return payments
    return extract_payment_amounts(text, ignore_prepay=False)


@router.message(in_main_group, in_preorder, F.text)
@router.message(in_main_group, in_preorder, F.caption)
async def handle_preorder(message: Message):
    """Топик «Предзаказы»: предоплата и/или блоки брони."""
    content = message.text or message.caption
    if not content:
        return

    if content.strip().startswith("/"):
        return

    if message.from_user and message.from_user.is_bot:
        return

    is_first_time = await mark_message_processed(message.chat.id, message.message_id)
    if not is_first_time:
        logger.info("Сообщение %s уже обработано, пропускаем.", message.message_id)
        return

    logger.info(
        "📋 preorder handler: msg=%s thread=%s",
        message.message_id,
        message.message_thread_id,
    )

    lines = content.strip().splitlines()
    booking_indices = [
        i
        for i, line in enumerate(lines)
        if re.match(r"^бронь\s*:?$", line.strip().lower())
    ]

    if booking_indices:
        preorder_lines = lines[: booking_indices[0]]
        if preorder_lines:
            payments = extract_prepayments("\n".join(preorder_lines))
            if any(payments.values()):
                try:
                    data = parse_client_data("\n".join(preorder_lines))
                    if data.get("phones") or data.get("full_name"):
                        await ClientRepository.get_or_create_client(
                            phone=data.get("main_phone"),
                            phones=data.get("phones"),
                            full_name=data.get("full_name"),
                            telegram_username=data.get("telegram_username"),
                            social_network=data.get("social_network"),
                            referral_source=data.get("referral_source"),
                        )
                except Exception as e:
                    logger.exception("Ошибка при сохранении клиента (предзаказ): %s", e)

                await StatsRepository.add_preorder(**payments)
                await PaymentService.add_payments_batch(payments, source_type="preorder")
                await safe_react(message, "👌")
                logger.info("Предзаказ обработан: %s", payments)

        for i, start_idx in enumerate(booking_indices):
            start = start_idx + 1
            end = (
                booking_indices[i + 1]
                if i + 1 < len(booking_indices)
                else len(lines)
            )
            booking_lines = lines[start:end]
            if not booking_lines:
                continue

            booking_payments = _booking_payments_from_block(booking_lines)

            try:
                result = await BookingService.process_booking(
                    booking_lines, booking_payments
                )
            except Exception as e:
                logger.exception("Ошибка при обработке блока брони: %s", e)
                await safe_react(message, "‼️")
                continue

            if not result.get("success"):
                if result.get("reason") == "no_items":
                    await safe_react(message, "‼️")
                    await send_and_clean(
                        bot=message.bot,
                        chat_id=message.chat.id,
                        text="❌ В блоке брони нет товаров с серийными номерами.",
                        reply_to_message_id=message.message_id,
                        message_thread_id=message.message_thread_id or _thread_preorder(),
                        delete_after=60,
                    )
                logger.warning("Блок брони не обработан: %s", result)
                continue

            # Оплаты брони в структуру дня (DailyPayment)
            if any(float(v or 0) > 0 for v in (booking_payments or {}).values()):
                try:
                    await PaymentService.add_payments_batch(
                        booking_payments, source_type="booking"
                    )
                    logger.info("💰 Платежи брони: %s", booking_payments)
                except Exception:
                    logger.exception("Не удалось записать платежи брони")

            await safe_react(message, "👍")
            booked_count = len(result.get("results", []))
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=f"✅ Добавлена бронь на {booked_count} товаров.",
                reply_to_message_id=message.message_id,
                message_thread_id=message.message_thread_id or _thread_preorder(),
                delete_after=60,
            )
            logger.info("Бронь успешно обработана: %s товаров", booked_count)

    else:
        payments = extract_prepayments(content)
        if any(payments.values()):
            try:
                data = parse_client_data(content)
                if data.get("phones") or data.get("full_name"):
                    await ClientRepository.get_or_create_client(
                        phone=data.get("main_phone"),
                        phones=data.get("phones"),
                        full_name=data.get("full_name"),
                        telegram_username=data.get("telegram_username"),
                        social_network=data.get("social_network"),
                        referral_source=data.get("referral_source"),
                    )
            except Exception as e:
                logger.exception("Ошибка при сохранении клиента (предзаказ): %s", e)

            await StatsRepository.add_preorder(**payments)
            await PaymentService.add_payments_batch(payments, source_type="preorder")
            await safe_react(message, "👌")
            logger.info("Предзаказ обработан: %s", payments)
        else:
            logger.info(
                "Сообщение %s не содержит предоплат — пропущено.", message.message_id
            )
