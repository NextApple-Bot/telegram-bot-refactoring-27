import asyncio
import logging
import os
import tempfile
from datetime import datetime
from typing import Optional

from aiogram import Bot
from aiogram.types import FSInputFile, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)


async def send_and_clean(
    bot: Bot,
    chat_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: str = "HTML",
    message_thread_id: Optional[int] = None,
    delete_after: Optional[int] = None,
) -> Message:
    """
    Отправляет сообщение и автоматически удаляет его через указанное время.
    Удобная обёртка для уменьшения дублирования кода.
    """
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
            message_thread_id=message_thread_id,
        )

        if delete_after and delete_after > 0:
            asyncio.create_task(_auto_delete_message(msg, delete_after))

        return msg

    except Exception as e:
        logger.error(f"Ошибка отправки сообщения в чат {chat_id}: {e}")
        # Попытка отправить без форматирования
        try:
            return await bot.send_message(
                chat_id=chat_id,
                text=text[:4000],
                message_thread_id=message_thread_id,
            )
        except Exception:
            logger.exception("Повторная ошибка отправки сообщения")
            return None


async def _auto_delete_message(message: Message, delay: int):
    """Фоновая задача для автоудаления сообщения."""
    try:
        await asyncio.sleep(delay)
        await message.delete()
    except Exception:
        pass  # сообщение уже удалено или чат не найден — нормально


async def save_temp_file(content: str, prefix: str = "bot_", suffix: str = ".txt") -> str:
    """
    Сохраняет текст во временный файл и возвращает путь.
    Автоматически удалять файл должен вызывающий код.
    """
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, prefix=prefix, delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            return f.name
    except Exception as e:
        logger.exception("Ошибка создания временного файла")
        raise


async def send_temp_document(
    bot: Bot,
    chat_id: int,
    content: str,
    filename: str,
    caption: str = "",
    message_thread_id: Optional[int] = None,
) -> Message | None:
    """Создаёт временный файл и сразу отправляет его как документ."""
    tmp_path = None
    try:
        tmp_path = await save_temp_file(content, suffix=".txt")

        document = FSInputFile(tmp_path, filename=filename)
        return await bot.send_document(
            chat_id=chat_id,
            document=document,
            caption=caption,
            message_thread_id=message_thread_id,
        )
    except Exception as e:
        logger.exception("Ошибка отправки временного документа")
        await send_and_clean(
            bot=bot,
            chat_id=chat_id,
            text="❌ Ошибка при формировании файла.",
            delete_after=60,
        )
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def format_date(dt: datetime | None) -> str:
    """Форматирование даты для красивого вывода."""
    if not dt:
        return "—"
    return dt.strftime("%d.%m.%Y %H:%M")


def format_price(price: int | float | None) -> str:
    """Красивое форматирование цены."""
    if price is None:
        return "0"
    return f"{int(price):,}".replace(",", " ")


def truncate(text: str, max_length: int = 100) -> str:
    """Обрезает текст с многоточием."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


# ==================== Markdown helpers ====================
def escape_markdown_v1(text: str) -> str:
    """Экранирование для MarkdownV1 (aiogram по умолчанию)."""
    if not text:
        return ""
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f"\\{char}")
    return text


def bold(text: str) -> str:
    return f"<b>{text}</b>"


def code(text: str) -> str:
    return f"<code>{text}</code>"
