import asyncio
import logging
import os
import signal
import sys
import time
import traceback

import uvicorn
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import text
from starlette.applications import Starlette
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Route

SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.asgi import SentryAsgiMiddleware
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        traces_sample_rate=1.0,
        environment=os.getenv("ENVIRONMENT", "production"),
        integrations=[StarletteIntegration(), FastApiIntegration()],
    )
    logging.info("✅ Sentry инициализирован")
else:
    logging.info("ℹ️ SENTRY_DSN не задан, мониторинг ошибок отключён")

log_format = os.getenv("LOG_FORMAT", "text").lower()
if log_format == "json":
    from pythonjsonlogger import jsonlogger
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logging.getLogger().handlers = [handler]
    logging.getLogger().setLevel(logging.INFO)
else:
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

        # FSM: Redis переживает рестарт; при ошибке — MemoryStorage
        storage = MemoryStorage()
        if bot_config.REDIS_URL:
            try:
                storage = RedisStorage.from_url(bot_config.REDIS_URL)
                self._redis_client = redis.from_url(
                    bot_config.REDIS_URL,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                )
                await self._redis_client.ping()
                logger.info("✅ RedisStorage для FSM + Redis ping OK")
            except Exception as e:
                logger.error(
                    "❌ Redis недоступен (%s). FSM на MemoryStorage. Проверьте REDIS_URL на Amvera.",
                    e,
                )
                storage = MemoryStorage()
                self._redis_client = None
        else:
            logger.warning(
                "⚠️ REDIS_URL не задан — MemoryStorage. "
                "Состояния FSM сбрасываются при рестарте. "
                "Добавьте Redis в Amvera и переменную REDIS_URL."
            )

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

    async def _setup_webhook(self, max_retries=5, base_delay=3):
        if not self.config.RENDER_URL:
            logger.warning("⚠️ RENDER_URL не задан — вебхук не будет установлен автоматически.")
            return
        webhook_url = f"{self.config.RENDER_URL}/webhook"
        for attempt in range(1, max_retries + 1):
            try:
                await self.bot.delete_webhook(drop_pending_updates=True)
                allowed_updates = self.dp.resolve_used_update_types()
                await self.bot.set_webhook(url=webhook_url, allowed_updates=allowed_updates)
                logger.info(f"✅ Вебхук установлен на {webhook_url}")
                return
            except Exception as e:
                logger.warning(f"⚠️ Попытка {attempt}/{max_retries} не удалась: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(base_delay * attempt)
                else:
                    logger.error("❌ Не удалось установить вебхук")

    async def shutdown(self):
        logger.info("🛑 Завершение работы...")
        try:
            if self.bot:
                try:
                    await self.bot.delete_webhook()
                    if hasattr(self.bot, "session") and self.bot.session:
                        try:
                            await self.bot.session.close()
                        except Exception as e:
                            logger.error(f"Ошибка при закрытии bot.session: {e}")
                except Exception as e:
                    logger.error(f"Ошибка при закрытии бота: {e}")

            if self._redis_client:
                try:
                    await self._redis_client.aclose()
                except Exception as e:
                    logger.error(f"Ошибка при закрытии Redis: {e}")

            from bot.db import dispose_engine
            await dispose_engine()
        except Exception as e:
            logger.error(f"Ошибка в shutdown: {e}")

    async def webhook(self, request: Request) -> Response:
        if not self.bot or not self.dp:
            return Response(status_code=503)
        try:
            from aiogram.types import Update
            update_data = await request.json()
            update = Update(**update_data)
            await self.dp.feed_update(bot=self.bot, update=update)
            return Response(status_code=200)
        except Exception as e:
            logger.exception(f"Ошибка обработки webhook: {e}")
            return Response(status_code=500)

    async def health(self, _: Request) -> Response:
        return PlainTextResponse("ok")

    async def health_detailed(self, _: Request) -> Response:
        from bot.db import check_db_health, check_redis_health
        start = time.monotonic()
        db_ok = await check_db_health()
        db_time = time.monotonic() - start
        start = time.monotonic()
        redis_ok = await check_redis_health()
        redis_time = time.monotonic() - start
        overall = db_ok  # redis optional for health
        return JSONResponse({
            "status": "healthy" if overall else "unhealthy",
            "database": {"status": "up" if db_ok else "down", "response_time_ms": round(db_time * 1000, 2) if db_ok else None},
            "redis": {"status": "up" if redis_ok else "down", "response_time_ms": round(redis_time * 1000, 2) if redis_ok else None},
        }, status_code=200 if overall else 503)


def create_starlette_app(app_instance):
    from starlette.routing import Route

    routes = [
        Route("/webhook", app_instance.webhook, methods=["POST"]),
        Route("/health", app_instance.health, methods=["GET"]),
        Route("/health/detailed", app_instance.health_detailed, methods=["GET"]),
        Route("/", lambda req: RedirectResponse(url="/admin/dashboard")),
    ]
    starlette_app = Starlette(routes=routes)

    Instrumentator().instrument(starlette_app).expose(starlette_app, endpoint="/metrics")

    if app_instance.config.SECRET_KEY:
        starlette_app.add_middleware(
            SessionMiddleware,
            secret_key=app_instance.config.SECRET_KEY,
            max_age=3600 * 24 * 7,
        )
        logger.info("✅ SessionMiddleware подключён")

    if app_instance.config.ADMIN_PASSWORD and app_instance.config.SECRET_KEY:
        try:
            from web_admin.main import app as admin_app
            starlette_app.mount("/admin", admin_app)
            logger.info("✅ Веб-админка смонтирована на /admin")
        except Exception as e:
            logger.error(f"❌ Не удалось смонтировать веб-админку: {e}")
    else:
        logger.warning("⚠️ Веб-админка не смонтирована (нет ADMIN_PASSWORD или SECRET_KEY)")

    return starlette_app


async def main_entry():
    app = Application()
    try:
        await app.initialize()
    except Exception:
        logger.critical("Не удалось инициализировать приложение.\n" + traceback.format_exc())
        sys.exit(1)

    starlette_app = create_starlette_app(app)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda: asyncio.create_task(app.shutdown()))

    port = int(os.getenv("PORT", "8000"))
    logger.info(f"🚀 Запуск сервера на порту {port}")
    config = uvicorn.Config(
        starlette_app,
        host="0.0.0.0",
        port=port,
        log_level="info",
        timeout_graceful_shutdown=30,
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main_entry())
