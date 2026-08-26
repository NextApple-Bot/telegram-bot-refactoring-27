import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, ReactionTypeEmoji
from sqlalchemy.exc import IntegrityError

from bot.db import get_async_session_factory
from bot.models import ProcessedMessage

logger = logging.getLogger(__name__)


async def is_message_processed(chat_id: int, message_id: int) -> bool:
    from sqlalchemy import select

    async_session = get_async_session_factory()
    async with async_session() as session:
        result = await session.execute(
            select(ProcessedMessage.id).where(
                ProcessedMessage.chat_id == chat_id,
                ProcessedMessage.message_id == message_id,
            )
        )
        return result.scalar_one_or_none() is not None


async def mark_message_processed(chat_id: int, message_id: int) -> bool:
    """
    Помечает сообщение обработанным.
    Returns:
        True  — первое обращение, можно обрабатывать
        False — уже было обработано (дубликат)
    """
    async_session = get_async_session_factory()
    try:
        async with async_session() as session:
            async with session.begin():
                session.add(ProcessedMessage(chat_id=chat_id, message_id=message_id))
        return True
    except IntegrityError:
        logger.debug(
            "Сообщение chat=%s msg=%s уже в processed_messages", chat_id, message_id
        )
        return False
    except Exception as e:
        logger.exception("Ошибка mark_message_processed: %s", e)
        return True


async def safe_react(message: Message, emoji: str) -> None:
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except TelegramBadRequest as e:
        if "REACTION_INVALID" in str(e) or "MESSAGE_REACTIONS_FORBIDDEN" in str(e):
            logger.warning("Не удалось поставить реакцию %s: %s", emoji, e)
        else:
            raise
