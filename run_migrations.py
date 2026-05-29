#!/usr/bin/env python
"""
Скрипт для применения миграций Alembic.
Используется в start.sh и вручную.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from alembic import command
from alembic.config import Config

# Добавляем корень проекта в PYTHONPATH
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

load_dotenv()

def run_migrations():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("❌ Ошибка: DATABASE_URL не найден в .env", file=sys.stderr)
        sys.exit(1)

    alembic_cfg = Config(str(BASE_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)

    print("🔄 Применяем миграции Alembic...")
    try:
        command.upgrade(alembic_cfg, "head")
        print("✅ Все миграции успешно применены!")
    except Exception as e:
        print(f"❌ Ошибка при применении миграций: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
