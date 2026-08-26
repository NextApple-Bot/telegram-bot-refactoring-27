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
from bot.utils.helpers import send_and_clean
from bot.utils.sort import sort_assortment_to_categories

logger = logging.getLogger(__name__)

router = Router()
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 МБ


def _read_text_bytes(raw: bytes) -> str:
    """Читает текст с перебором кодировок."""
    for enc in ("utf-8-sig", "utf-8", "cp1251", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _is_txt_document(document) -> bool:
    if not document:
        return False
    name = (document.file_name or "").lower()
    mime = (document.mime_type or "").lower()
    if name.endswith(".txt"):
        return True
    if mime in ("text/plain", "application/octet-stream", "text/txt"):
        return True
    return False


@router.message(
    F.message_thread_id == config.THREAD_ASSORTMENT,
    F.chat.id == config.MAIN_GROUP_ID,
)
async def handle_assortment_upload(message: Message, state: FSMContext) -> None:
    """
    Загрузка ассортимента в топик (текст или .txt).
    Всегда отвечает пользователю — даже при ошибке.
    """
    # Игнорируем служебные сообщения бота
    if message.from_user and message.from_user.is_bot:
        return

    # Нужен текст, подпись или документ
    if not (message.text or message.caption or message.document):
        return

    user_id = getattr(message.from_user, "id", "unknown")
    logger.info("📥 Загрузка ассортимента от user_id=%s msg_id=%s", user_id, message.message_id)

    try:
        # Сброс зависшего состояния: новая загрузка всегда принимается
        current_state = await state.get_state()
        if current_state == AssortmentConfirmState.waiting_for_confirm.state:
            logger.info("Сбрасываем предыдущее неподтверждённое состояние ассортимента")
            await state.clear()

        content: str | None = None

        # === Файл ===
        if message.document:
            document = message.document

            if document.file_size and document.file_size > MAX_FILE_SIZE:
                await message.reply(
                    "❌ Файл слишком большой (максимум 10 МБ).",
                    message_thread_id=config.THREAD_ASSORTMENT,
                )
                return

            if not _is_txt_document(document):
                await message.reply(
                    "⚠️ Нужен текстовый файл (.txt).\n"
                    f"Сейчас: {document.file_name or 'без имени'} ({document.mime_type or 'unknown'}).",
                    message_thread_id=config.THREAD_ASSORTMENT,
                )
                return

            safe_name = re.sub(r"[^\w.\-]+", "_", document.file_name or "assortment.txt")[:80]
            file_path = os.path.join(tempfile.gettempdir(), f"assort_{uuid.uuid4().hex}_{safe_name}")

            try:
                await message.bot.download(document, destination=file_path)
                async with aiofiles.open(file_path, "rb") as f:
                    raw = await f.read()
                content = _read_text_bytes(raw)
            except Exception as e:
                logger.exception("Ошибка скачивания/чтения файла ассортимента")
                await message.reply(
                    f"❌ Не удалось прочитать файл: {e}",
                    message_thread_id=config.THREAD_ASSORTMENT,
                )
                return
            finally:
                if os.path.exists(file_path):
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

        # === Текст / caption ===
        else:
            content = (message.text or message.caption or "").strip()

        if not content or not content.strip():
            await message.reply(
                "⚠️ Пустой файл/сообщение. Отправьте текст или .txt с ассортиментом.",
                message_thread_id=config.THREAD_ASSORTMENT,
            )
            return

        # === Парсинг ===
        try:
            categories = sort_assortment_to_categories(content)
        except Exception as e:
            logger.exception("Ошибка парсинга ассортимента")
            await message.reply(
                f"❌ Ошибка разбора файла: {e}",
                message_thread_id=config.THREAD_ASSORTMENT,
            )
            return

        if not categories:
            preview = "\n".join(content.splitlines()[:8])[:500]
            await message.reply(
                "❌ Не удалось распознать категории.\n\n"
                "Нужен формат:\n"
                "<code>------------\n"
                "iPhone:\n"
                "------------\n"
                "iPhone 16 (SN123)</code>\n\n"
                f"Начало файла:\n<code>{preview}</code>",
                parse_mode="HTML",
                message_thread_id=config.THREAD_ASSORTMENT,
            )
            return

        total_items = sum(len(cat.get("items", []) or []) for cat in categories)
        empty_cats = sum(1 for cat in categories if not (cat.get("items") or []))
        logger.info(
            "📦 Распознано categories=%s items=%s empty=%s",
            len(categories),
            total_items,
            empty_cats,
        )

        await state.update_data(temp_categories=categories)
        await state.set_state(AssortmentConfirmState.waiting_for_confirm)

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

        await message.reply(
            f"📦 <b>Ассортимент получен</b>\n\n"
            f"Категорий: <b>{len(categories)}</b>"
            f" (пустых: {empty_cats})\n"
            f"Товаров: <b>{total_items}</b>\n\n"
            f"⚠️ Это <b>полностью заменит</b> текущий ассортимент в базе.\n"
            f"Подтверждаете?",
            reply_markup=keyboard,
            parse_mode="HTML",
            message_thread_id=config.THREAD_ASSORTMENT,
        )

    except Exception as e:
        logger.exception("Критическая ошибка в handle_assortment_upload")
        try:
            await message.reply(
                f"❌ Ошибка обработки ассортимента: {e}",
                message_thread_id=config.THREAD_ASSORTMENT,
            )
        except Exception:
            pass


@router.callback_query(F.data.startswith("assort_confirm:"))
async def process_assortment_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Подтверждение замены ассортимента.
    Работает даже если FSM-состояние потерялось (данные из state, иначе — отказ).
    """
    try:
        await callback.answer()
    except Exception:
        pass

    action = (callback.data or "").split(":")[-1]
    data = await state.get_data()
    categories = data.get("temp_categories") or []

    if action == "yes":
        if not categories:
            try:
                await callback.message.edit_text(
                    "❌ Нет данных для замены (сессия устарела).\n"
                    "Отправьте файл ассортимента ещё раз."
                )
            except Exception:
                await callback.message.answer(
                    "❌ Нет данных для замены. Отправьте файл ещё раз."
                )
            await state.clear()
            return

        try:
            logger.info("🔄 Замена ассортимента: %s категорий", len(categories))
            await ItemRepository.bulk_replace_assortment(categories)
            await AssortmentService.invalidate_cache()
            total = sum(len(c.get("items", []) or []) for c in categories)
            text = (
                f"✅ Ассортимент успешно заменён.\n"
                f"Категорий: {len(categories)}, товаров: {total}."
            )
            try:
                await callback.message.edit_text(text)
            except Exception:
                await callback.message.answer(text)
            logger.info("✅ Ассортимент заменён")
        except Exception as e:
            logger.exception("Ошибка при сохранении ассортимента")
            err = f"❌ Ошибка при сохранении: {e}"
            try:
                await callback.message.edit_text(err)
            except Exception:
                await callback.message.answer(err)
    else:
        try:
            await callback.message.edit_text("❌ Замена ассортимента отменена.")
        except Exception:
            await callback.message.answer("❌ Замена ассортимента отменена.")

    await state.clear()
