import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import Update
from fastapi import FastAPI
from sqlalchemy import text  # ← добавлен импорт
from starlette.middleware.sessions import SessionMiddleware

from bot import config
from bot.background import start_background_tasks
from bot.db import dispose_engine, get_async_session_factory, init_db
from bot.handlers.topics import topics_router
from bot.middleware.error_handler import ErrorHandlerMiddleware
from bot.webhook_utils import check_and_set_webhook

from web_admin.main import app as admin_app

logger = logging.getLogger(__name__)


# ============================================================
# FSM Storage
# ============================================================

def get_storage():
    """Выбор хранилища FSM в зависимости от режима масштабирования."""
    if os.getenv("SCALING_ENABLED", "false").lower() == "true" and config.REDIS_URL:
        logger.info("🔄 Используется RedisStorage для FSM (SCALING_ENABLED=true)")
        return RedisStorage.from_url(config.REDIS_URL)
    logger.info("📦 Используется MemoryStorage для FSM")
    return MemoryStorage()


# ============================================================
# Bot и Dispatcher
# ============================================================

bot = Bot(token=config.BOT_TOKEN)
storage = get_storage()
dp = Dispatcher(storage=storage)

# Глобальный обработчик ошибок
dp.message.middleware(ErrorHandlerMiddleware())
dp.callback_query.middleware(ErrorHandlerMiddleware())
dp.inline_query.middleware(ErrorHandlerMiddleware())

# ============================================================
# Подключение роутеров (с защитой от повторного подключения)
# ============================================================
if topics_router.parent_router is None:
    dp.include_router(topics_router)
else:
    logger.warning(
        f"topics_router уже привязан к {topics_router.parent_router!r}, "
        "повторное подключение пропущено"
    )


# ============================================================
# Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # === STARTUP ===
    logger.info("🚀 Запуск приложения...")

    # 1. Инициализация БД
    await init_db()

    # 2. Проверка подключения к БД
    try:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))  # ← обёрнуто в text()
        logger.info("✅ База данных доступна")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД при старте: {e}")
        raise

    # 3. Запуск фоновых задач
    await start_background_tasks(bot, dp)

    # 4. Настройка вебхука
    if config.RENDER_URL:
        await check_and_set_webhook(bot, dp)
    else:
        logger.warning("⚠️ RENDER_URL не задан — webhook не будет установлен")

    logger.info("✅ Приложение успешно запущено")
    yield

    # === SHUTDOWN ===
    logger.info("🛑 Остановка приложения...")
    await dispose_engine()
    logger.info("✅ Ресурсы освобождены")


# ============================================================
# FastAPI приложение
# ============================================================

app = FastAPI(
    title="Telegram Bot + Admin Panel",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    max_age=3600 * 24 * 30,
)

app.mount("/admin", admin_app)


# ============================================================
# Эндпоинты
# ============================================================

@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy"}


@app.get("/health/db")
async def db_health_check() -> dict[str, Any]:
    try:
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))  # ← обёрнуто в text()
        return {"database": "healthy"}
    except Exception as e:
        return {"database": "unhealthy", "error": str(e)}


@app.post("/webhook")
async def telegram_webhook(update: dict[str, Any]) -> dict[str, bool]:
    """
    Обработчик обновлений от Telegram.
    Всегда возвращает 200 OK, чтобы Telegram не повторял запрос при ошибках.
    """
    try:
        telegram_update = Update.model_validate(update)
        await dp.feed_update(bot, telegram_update)

    except TelegramBadRequest as e:
        logger.warning(f"TelegramBadRequest при обработке обновления: {e}")

    except TelegramAPIError as e:
        logger.error(f"TelegramAPIError при обработке обновления: {e}")

    except Exception as e:
        logger.exception(f"Необработанная ошибка в webhook: {e}")

    return {"ok": True}


# ============================================================
# Локальный запуск
# ============================================================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=config.PORT,
        reload=False,
        log_level="info",
    )
