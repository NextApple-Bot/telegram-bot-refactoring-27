import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message, ReactionTypeEmoji

from bot.db import get_async_session_factory
from bot.models import ProcessedMessage

logger = logging.getLogger(__name__)


async def is_message_processed(chat_id: int, message_id: int) -> bool:
    async_session = get_async_session_factory()
    async with async_session() as session:
        result = await session.execute(
            "SELECT 1 FROM processed_messages WHERE chat_id = :chat_id AND message_id = :msg_id",
            {"chat_id": chat_id, "msg_id": message_id}
        )
        return result.fetchone() is not None


async def mark_message_processed(chat_id: int, message_id: int) -> bool:
    async_session = get_async_session_factory()
    async with async_session() as session, session.begin():
        try:
            session.add(ProcessedMessage(chat_id=chat_id, message_id=message_id))
            return True
        except Exception:
            await session.rollback()
            return False


async def safe_react(message: Message, emoji: str) -> None:
    try:
        await message.react([ReactionTypeEmoji(emoji=emoji)])
    except TelegramBadRequest as e:
        if "REACTION_INVALID" in str(e) or "MESSAGE_REACTIONS_FORBIDDEN" in str(e):
            logger.warning(f"Не удалось поставить реакцию {emoji}: {e}")
        else:
            raise
