# Файл: alembic/env.py
import asyncio
import importlib.util
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

load_dotenv()

# --- Поиск bot/models.py ---
root_path = Path(__file__).parent.parent
models_path = root_path / "bot" / "models.py"

if not models_path.exists():
    print(f"❌ Файл models.py не найден по пути: {models_path}")
    os.system("ls -la /app/bot")
    raise FileNotFoundError(f"models.py not found at {models_path}")

print(f"✅ Загружаем модели из: {models_path}")
spec = importlib.util.spec_from_file_location("bot.models", models_path)
models_module = importlib.util.module_from_spec(spec)
sys.modules["bot.models"] = models_module
spec.loader.exec_module(models_module)

if not hasattr(models_module, "Base"):
    raise AttributeError("Модуль models.py не содержит атрибут 'Base'")

Base = models_module.Base
# ---------------------------------

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set")

# Принудительно заменяем postgresql:// на postgresql+asyncpg://
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    print("🔄 Заменён синхронный URL на асинхронный")

config.set_main_option("sqlalchemy.url", DATABASE_URL)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
