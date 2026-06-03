import asyncio
import logging
import os
import sys
import traceback

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class Application:
    def __init__(self):
        self.bot = None
        self.dp = None
        self.config = None
        self._redis_client = None

    async def initialize(self):
        import redis.asyncio as redis
        from aiogram import Bot, Dispatcher
        from aiogram.fsm.storage.memory import MemoryStorage
        from aiogram.fsm.storage.redis import RedisStorage

        from bot.config import config as bot_config
        from bot.db import get_async_session_factory
        from bot.middleware.error_handler import ErrorHandlerMiddleware

        self.config = bot_config
        logger.info("✅ Конфигурация загружена")

        self.bot = Bot(token=bot_config.BOT_TOKEN)
        logger.info("✅ Экземпляр Bot создан")

        if bot_config.REDIS_URL:
            self._redis_client = redis.from_url(bot_config.REDIS_URL, decode_responses=True)
            storage = RedisStorage(redis=self._redis_client)
            logger.info("✅ RedisStorage для FSM")
        else:
            storage = MemoryStorage()

        self.dp = Dispatcher(storage=storage)
        self.dp.update.middleware(ErrorHandlerMiddleware())
        logger.info("✅ Диспетчер создан")

        from bot.handlers import router
        self.dp.include_router(router)
        logger.info("✅ Роутер подключён")

        async_session = get_async_session_factory()
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        logger.info("✅ Подключение к БД подтверждено")

        from bot.background import start_background_tasks
        asyncio.create_task(start_background_tasks(self.bot, self.dp))
        logger.info("✅ Фоновые задачи запущены")

        await self._setup_webhook()
        return self

    async def _setup_webhook(self):
        if not self.config.RENDER_URL:
            return
        webhook_url = f"{self.config.RENDER_URL}/webhook"
        try:
            await self.bot.delete_webhook(drop_pending_updates=True)
            allowed_updates = self.dp.resolve_used_update_types()
            await self.bot.set_webhook(url=webhook_url, allowed_updates=allowed_updates)
            logger.info(f"✅ Вебхук установлен на {webhook_url}")
        except Exception as e:
            logger.error(f"❌ Ошибка установки вебхука: {e}")

    async def webhook(self, request: Request) -> Response:
        if not self.bot or not self.dp:
            return Response(status_code=503)
        try:
            from aiogram.types import Update
            update = Update(**(await request.json()))
            await self.dp.feed_update(self.bot, update)
            return Response(status_code=200)
        except Exception:
            logger.exception("❌ Ошибка вебхука")
            return Response(status_code=500)

    async def health(self, _: Request) -> Response:
        return PlainTextResponse("OK")


# ============================================================
# Starlette + Админка
# ============================================================
def create_starlette_app(app_instance):
    routes = [
        Route("/webhook", app_instance.webhook, methods=["POST"]),
        Route("/health", app_instance.health, methods=["GET"]),
    ]
    starlette_app = Starlette(routes=routes)

    if app_instance.config.SECRET_KEY:
        starlette_app.add_middleware(SessionMiddleware, secret_key=app_instance.config.SECRET_KEY)
        logger.info("✅ SessionMiddleware добавлена")

    # Монтируем админку
    try:
        from web_admin.main import app as admin_app
        starlette_app.mount("/admin", admin_app)
        logger.info("✅ Веб-админка смонтирована на /admin")
    except Exception as e:
        logger.error(f"❌ Не удалось смонтировать веб-админку: {e}")

    return starlette_app


async def main_entry():
    app = Application()
    await app.initialize()

    starlette_app = create_starlette_app(app)

    port = int(os.getenv("PORT", "10000"))
    logger.info(f"🚀 Запуск сервера на порту {port}")

    config = uvicorn.Config(
        starlette_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        workers=1,
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main_entry())
