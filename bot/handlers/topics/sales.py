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
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)
router = Router()

TRADE_IN_PATTERNS = [
    r"trade\s*in",
    r"трейд\s*ин",
    r"trade\-in",
]


def remove_trade_in_lines(text: str) -> str:
    lines = text.splitlines()
    filtered = [
        line
        for line in lines
        if not any(re.search(p, line, re.IGNORECASE) for p in TRADE_IN_PATTERNS)
    ]
    return "\n".join(filtered)


def _in_sales_topic(message: Message) -> bool:
    try:
        got = message.message_thread_id
        expected = int(config.THREAD_SALES)
        if got is None:
            return False
        return int(got) == expected
    except (TypeError, ValueError):
        return False


@router.message(F.text)
@router.message(F.caption)
async def handle_sales_message(message: Message) -> None:
    """
    Обработчик продаж в топике THREAD_SALES.
    Пересланные сообщения тоже обрабатываются.
    """
    try:
        if int(message.chat.id) != int(config.MAIN_GROUP_ID):
            return
    except (TypeError, ValueError):
        return

    if not _in_sales_topic(message):
        return

    if message.from_user and message.from_user.is_bot:
        return

    content = message.text or message.caption
    if not content or not content.strip():
        return

    # Команды не трогаем
    if content.strip().startswith("/"):
        return

    logger.info(
        "🛒 sales handler: msg=%s user=%s forward=%s serials_preview=%s",
        message.message_id,
        getattr(message.from_user, "id", None),
        bool(
            getattr(message, "forward_date", None)
            or getattr(message, "forward_origin", None)
        ),
        extract_serials(content)[:5],
    )

    try:
        is_first_time = await mark_message_processed(message.chat.id, message.message_id)
        if not is_first_time:
            logger.debug("Сообщение %s уже обработано", message.message_id)
            return

        content = remove_trade_in_lines(content)
        payments = extract_payment_amounts(content, ignore_prepay=True)

        result = await SaleService.process_sale(
            content=content,
            chat_id=message.chat.id,
            message_id=message.message_id,
            payments=payments,
        )

        if result.get("skipped"):
            logger.info("Продажа пропущена msg=%s", message.message_id)
            return

        # Клиент
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
                    birth_date=data.get("birth_date"),
                )
        except Exception as e:
            logger.exception("Ошибка сохранения клиента: %s", e)

        # Платежи
        if not result.get("skip_payments", False):
            try:
                await PaymentService.add_payments_batch(payments, source_type="sale")
                logger.info("💰 Платежи: %s", payments)
            except Exception as e:
                logger.exception("Ошибка сохранения платежей: %s", e)

        # Реакции
        if result.get("is_accessory"):
            await safe_react(message, "⚡️")
            logger.info("Аксессуар msg=%s", message.message_id)
        elif result.get("sold_items"):
            await safe_react(message, "🔥")
            logger.info(
                "✅ Продажа: %s товаров msg=%s",
                len(result["sold_items"]),
                message.message_id,
            )
        elif result.get("not_found"):
            await safe_react(message, "‼️")
            text = (
                "❌ Серийные номера не найдены в ассортименте:\n"
                + "\n".join(result["not_found"])
            )
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=text,
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_SALES,
                delete_after=60,
            )
            logger.warning("SN не найдены msg=%s: %s", message.message_id, result["not_found"])
        else:
            await safe_react(message, "👀")
            logger.info("Обработано без действий msg=%s", message.message_id)

    except Exception as e:
        logger.exception("Критическая ошибка sales handler: %s", e)
        try:
            await safe_react(message, "‼️")
            await send_and_clean(
                bot=message.bot,
                chat_id=message.chat.id,
                text=f"❌ Ошибка обработки продажи: {e}",
                reply_to_message_id=message.message_id,
                message_thread_id=config.THREAD_SALES,
                delete_after=90,
            )
        except Exception:
            pass
