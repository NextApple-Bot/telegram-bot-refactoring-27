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
from sqlalchemy import text
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
        logger.info("Используется RedisStorage для FSM (SCALING_ENABLED=true)")
        return RedisStorage.from_url(config.REDIS_URL)
    logger.info("Используется MemoryStorage для FSM")
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
dp.my_chat_member.middleware(ErrorHandlerMiddleware())
dp.chat_member.middleware(ErrorHandlerMiddleware())

# Защита от повторного подключения роутера
if topics_router.parent_router is None:
    dp.include_router(topics_router)
else:
    logger.warning(
        f"topics_router уже привязан к {topics_router.parent_router!r}. "
        "Повторное подключение пропущено."
    )


# ============================================================
# Lifespan (Startup / Shutdown)
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Управление жизненным циклом приложения."""
    logger.info("🚀 Запуск приложения...")

    # === STARTUP ===
    try:
        # 1. Инициализация базы данных
        await init_db()
        logger.info("✅ Инициализация БД завершена")

        # 2. Проверка подключения к БД
        session_factory = get_async_session_factory()
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        logger.info("✅ База данных доступна")

        # 3. Запуск фоновых задач
        await start_background_tasks(bot, dp)
        logger.info("✅ Фоновые задачи запущены")

        # 4. Настройка вебхука
        if config.RENDER_URL:
            await check_and_set_webhook(bot, dp)
        else:
            logger.warning("RENDER_URL не задан — webhook не будет установлен")

        logger.info("✅ Приложение успешно запущено")

    except Exception as e:
        logger.exception("❌ Критическая ошибка при запуске приложения")
        raise

    yield  # Приложение работает

    # === SHUTDOWN ===
    logger.info("🛑 Остановка приложения...")
    try:
        await bot.session.close()
        logger.info("✅ Сессия бота закрыта")
    except Exception as e:
        logger.warning(f"Ошибка при закрытии сессии бота: {e}")

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
            await session.execute(text("SELECT 1"))
        return {"database": "healthy"}
    except Exception as e:
        logger.error(f"DB healthcheck failed: {e}")
        return {"database": "unhealthy", "error": str(e)}


@app.post("/webhook")
async def telegram_webhook(update: dict[str, Any]) -> dict[str, bool]:
    """
    Обработчик обновлений от Telegram.
    Всегда возвращает 200, чтобы Telegram не повторял запрос.
    """
    try:
        telegram_update = Update.model_validate(update)
        await dp.feed_update(bot, telegram_update)

    except TelegramBadRequest as e:
        logger.warning(f"TelegramBadRequest: {e}")

    except TelegramAPIError as e:
        logger.error(f"TelegramAPIError: {e}")

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
