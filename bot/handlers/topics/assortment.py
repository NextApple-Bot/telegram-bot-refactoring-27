import logging
import os
import re
import tempfile
import uuid

import aiofiles
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot import config
from bot.handlers.states import AssortmentConfirmState
from bot.repositories.item import ItemRepository
from bot.services.assortment import AssortmentService
from bot.utils.sort import sort_assortment_to_categories

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024


def _thread_id() -> int:
    try:
        return int(config.THREAD_ASSORTMENT)
    except (TypeError, ValueError):
        return 0


def _in_assortment_topic(message: Message) -> bool:
    """Мягкая проверка топика (int-сравнение, логирование)."""
    got = message.message_thread_id
    expected = _thread_id()
    ok = got is not None and int(got) == expected
    if not ok:
        logger.debug(
            "assortment skip: thread got=%s expected=%s chat=%s",
            got,
            expected,
            getattr(message.chat, "id", None),
        )
    return ok


def _read_text_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _is_txt_document(document) -> bool:
    if not document:
        return False
    name = (document.file_name or "").lower().strip()
    mime = (document.mime_type or "").lower()
    if name.endswith(".txt"):
        return True
    if mime.startswith("text/"):
        return True
    if mime in ("application/octet-stream", "application/txt"):
        return True
    return False


async def _reply(message: Message, text: str, **kwargs) -> None:
    """
    Ответ в тот же forum-топик.
    Используем bot.send_message — у message.answer() в aiogram
    message_thread_id уже подставляется из сообщения, из-за чего
    явная передача даёт TypeError: multiple values for message_thread_id.
    """
    thread = message.message_thread_id or _thread_id()
    kwargs.pop("message_thread_id", None)
    try:
        await message.bot.send_message(
            chat_id=message.chat.id,
            text=text,
            message_thread_id=thread,
            **kwargs,
        )
    except Exception:
        logger.exception("Не удалось отправить ответ в топик ассортимента")


@router.message(F.document)
@router.message(F.text)
@router.message(F.caption)
async def handle_assortment_upload(message: Message, state: FSMContext) -> None:
    """
    Любой текст/файл в топике «Ассортимент» основной группы.
    Пересланные файлы тоже обрабатываются.
    """
    try:
        if int(message.chat.id) != int(config.MAIN_GROUP_ID):
            return
    except (TypeError, ValueError):
        return

    if not _in_assortment_topic(message):
        return

    if message.from_user and message.from_user.is_bot:
        return

    if not (message.document or message.text or message.caption):
        return

    text_head = (message.text or "").strip()
    if text_head.startswith("/") and not message.document:
        return

    user_id = getattr(message.from_user, "id", None)
    logger.info(
        "📥 assortment handler: user=%s msg=%s doc=%s forward=%s thread=%s",
        user_id,
        message.message_id,
        bool(message.document),
        bool(getattr(message, "forward_date", None) or getattr(message, "forward_origin", None)),
        message.message_thread_id,
    )

    try:
        try:
            if await state.get_state() == AssortmentConfirmState.waiting_for_confirm.state:
                await state.clear()
        except Exception:
            logger.warning("Не удалось проверить/очистить FSM state", exc_info=True)
            try:
                await state.clear()
            except Exception:
                pass

        content: str | None = None

        if message.document:
            document = message.document
            fname = document.file_name or "без_имени"

            if document.file_size and document.file_size > MAX_FILE_SIZE:
                await _reply(message, "❌ Файл слишком большой (максимум 10 МБ).")
                return

            if not _is_txt_document(document):
                await _reply(
                    message,
                    f"⚠️ Нужен текстовый файл (.txt).\nСейчас: {fname} ({document.mime_type or '?'}).",
                )
                return

            safe_name = re.sub(r"[^\w.\-]+", "_", fname)[:80] or "assortment.txt"
            file_path = os.path.join(
                tempfile.gettempdir(), f"assort_{uuid.uuid4().hex}_{safe_name}"
            )

            try:
                await message.bot.download(document, destination=file_path)
                async with aiofiles.open(file_path, "rb") as f:
                    raw = await f.read()
                content = _read_text_bytes(raw)
            except Exception as e:
                logger.exception("Ошибка скачивания файла ассортимента")
                await _reply(message, f"❌ Не удалось прочитать файл: {e}")
                return
            finally:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
        else:
            content = (message.text or message.caption or "").strip()

        if not content or not content.strip():
            await _reply(message, "⚠️ Пустой файл. Отправьте .txt с ассортиментом.")
            return

        try:
            categories = sort_assortment_to_categories(content)
        except Exception as e:
            logger.exception("Ошибка парсинга ассортимента")
            await _reply(message, f"❌ Ошибка разбора файла: {e}")
            return

        if not categories:
            preview = "\n".join(content.splitlines()[:6])[:400]
            await _reply(
                message,
                "❌ Не удалось распознать категории.\n\n"
                "Формат:\n"
                "<code>------------\niPhone:\n------------\niPhone 16 (SN)</code>\n\n"
                f"Начало файла:\n<code>{preview}</code>",
                parse_mode="HTML",
            )
            return

        total_items = sum(len(cat.get("items") or []) for cat in categories)
        empty_cats = sum(1 for cat in categories if not (cat.get("items") or []))
        logger.info(
            "📦 categories=%s items=%s empty=%s",
            len(categories),
            total_items,
            empty_cats,
        )

        try:
            await state.update_data(temp_categories=categories)
            await state.set_state(AssortmentConfirmState.waiting_for_confirm)
        except Exception:
            logger.exception("FSM save failed — продолжаем без state, confirm может не сработать")

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Подтвердить замену",
                        callback_data="assort_confirm:yes",
                    ),
                    InlineKeyboardButton(
                        text="❌ Отмена",
                        callback_data="assort_confirm:no",
                    ),
                ]
            ]
        )

        await _reply(
            message,
            f"📦 <b>Ассортимент получен</b>\n\n"
            f"Категорий: <b>{len(categories)}</b> (пустых: {empty_cats})\n"
            f"Товаров: <b>{total_items}</b>\n\n"
            f"⚠️ Это <b>полностью заменит</b> текущий ассортимент.\n"
            f"Подтверждаете?",
            reply_markup=keyboard,
            parse_mode="HTML",
        )

    except Exception as e:
        logger.exception("Критическая ошибка assortment upload")
        await _reply(message, f"❌ Ошибка обработки: {e}")


@router.callback_query(F.data.startswith("assort_confirm:"))
async def process_assortment_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        await callback.answer()
    except Exception:
        pass

    action = (callback.data or "").split(":")[-1]
    try:
        data = await state.get_data()
    except Exception:
        data = {}
    categories = data.get("temp_categories") or []

    async def _edit_or_send(text: str) -> None:
        try:
            await callback.message.edit_text(text)
        except Exception:
            try:
                thread = callback.message.message_thread_id or _thread_id()
                await callback.bot.send_message(
                    chat_id=callback.message.chat.id,
                    text=text,
                    message_thread_id=thread,
                )
            except Exception:
                logger.exception("Не удалось ответить на confirm")

    if action == "yes":
        if not categories:
            await _edit_or_send(
                "❌ Нет данных (сессия устарела). Отправьте файл ассортимента ещё раз."
            )
            try:
                await state.clear()
            except Exception:
                pass
            return

        try:
            logger.info("🔄 Замена ассортимента: %s категорий", len(categories))
            await ItemRepository.bulk_replace_assortment(categories)
            await AssortmentService.invalidate_cache()
            total = sum(len(c.get("items") or []) for c in categories)
            await _edit_or_send(
                f"✅ Ассортимент успешно заменён.\n"
                f"Категорий: {len(categories)}, товаров: {total}."
            )
        except Exception as e:
            logger.exception("Ошибка сохранения ассортимента")
            await _edit_or_send(f"❌ Ошибка при сохранении: {e}")
    else:
        await _edit_or_send("❌ Замена ассортимента отменена.")

    try:
        await state.clear()
    except Exception:
        pass
