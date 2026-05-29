# Файл: bot/db.py
import asyncio
import logging
import os
from functools import wraps

import asyncpg

from bot import config

logger = logging.getLogger(__name__)


def retry_on_db_error(retries=3, delay=1, backoff=2):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(retries):
                try:
                    return await func(*args, **kwargs)
                except (asyncpg.exceptions.ConnectionFailureError,
                        asyncpg.exceptions.InterfaceError,
                        asyncpg.exceptions.PostgresConnectionError) as e:
                    last_exception = e
                    if attempt < retries - 1:
                        wait = delay * (backoff ** attempt)
                        logger.warning(f"Ошибка БД (попытка {attempt+1}/{retries}): {e}. Повтор через {wait}с")
                        await asyncio.sleep(wait)
                    else:
                        logger.error(f"Все попытки исчерпаны: {e}")
                        raise
                except Exception:
                    raise
            raise last_exception
        return wrapper
    return decorator


_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        min_size = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
        max_size = int(os.getenv("DB_POOL_MAX_SIZE", "5"))
        last_exception = None
        for attempt in range(5):
            try:
                _pool = await asyncpg.create_pool(
                    config.DATABASE_URL,
                    min_size=min_size,
                    max_size=max_size,
                    command_timeout=60,
                    max_inactive_connection_lifetime=300
                )
                logger.info(f"✅ Пул соединений создан (min={min_size}, max={max_size})")
                break
            except Exception as e:
                last_exception = e
                wait = 2 ** attempt
                logger.warning(f"Не удалось создать пул (попытка {attempt+1}/5): {e}. Повтор через {wait}с")
                await asyncio.sleep(wait)
        else:
            logger.error("Все попытки создания пула провалились")
            raise last_exception
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("✅ Пул соединений закрыт")


async def init_db():
    """Создаёт все таблицы, индексы и недостающие колонки."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Таблица категорий
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS categories (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            )
        ''')
        # Таблица товаров
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                text TEXT NOT NULL,
                serial TEXT,
                category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
                is_booked BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица продаж
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id SERIAL PRIMARY KEY,
                item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
                count INTEGER DEFAULT 1,
                cash REAL DEFAULT 0,
                terminal REAL DEFAULT 0,
                qr REAL DEFAULT 0,
                transfer REAL DEFAULT 0,
                invoice REAL DEFAULT 0,
                installment REAL DEFAULT 0,
                is_accessory BOOLEAN DEFAULT FALSE,
                message_id BIGINT UNIQUE,
                sold_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица предзаказов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS preorders (
                id SERIAL PRIMARY KEY,
                cash REAL DEFAULT 0,
                terminal REAL DEFAULT 0,
                qr REAL DEFAULT 0,
                transfer REAL DEFAULT 0,
                invoice REAL DEFAULT 0,
                installment REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица броней
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id SERIAL PRIMARY KEY,
                item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                total_amount REAL DEFAULT 0,
                booked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица клиентов
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS clients (
                id SERIAL PRIMARY KEY,
                full_name TEXT,
                phone TEXT UNIQUE,
                phones TEXT,
                telegram_username TEXT,
                social_network TEXT,
                referral_source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица покупок
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                client_id INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
                items_json TEXT,
                total_amount REAL,
                payment_details JSONB,
                purchase_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # Таблица удалённых товаров
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS deleted_items (
                id SERIAL PRIMARY KEY,
                item_id INTEGER REFERENCES items(id) ON DELETE SET NULL,
                text TEXT NOT NULL,
                serial TEXT,
                category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
                deleted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                restored BOOLEAN DEFAULT FALSE,
                reason TEXT,
                sale_message_id BIGINT
            )
        ''')
        # Таблица обработанных сообщений
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS processed_messages (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                message_id INTEGER NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, message_id)
            )
        ''')
        # Таблица ежедневных платежей
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_payments (
                id SERIAL PRIMARY KEY,
                type TEXT NOT NULL,
                payment_type TEXT NOT NULL,
                amount REAL NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sale_message_id BIGINT,
                CHECK (type IN ('sale', 'preorder')),
                CHECK (payment_type IN ('cash', 'terminal', 'qr', 'transfer', 'invoice', 'installment'))
            )
        ''')

        # Индексы
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_phone ON clients(phone)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_client ON purchases(client_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_categories_lower_name ON categories(LOWER(name))')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_serial ON items(serial)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_created_at ON clients(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_purchases_created_at ON purchases(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_is_booked ON items(is_booked)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_deleted_items_deleted_at ON deleted_items(deleted_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_deleted_items_restored ON deleted_items(restored)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_daily_payments_created_at ON daily_payments(created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_processed_messages_processed_at ON processed_messages(processed_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_sales_item_id ON sales(item_id)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_clients_updated_at ON clients(updated_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_daily_payments_type ON daily_payments(type)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_processed_messages_chat_processed ON processed_messages(chat_id, processed_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_items_category_booked_created ON items(category_id, is_booked, created_at)')
        await conn.execute('CREATE INDEX IF NOT EXISTS idx_daily_payments_sale_message_id ON daily_payments(sale_message_id)')

        # Добавление новых колонок (совместимость)
        await conn.execute('ALTER TABLE preorders ADD COLUMN IF NOT EXISTS transfer REAL DEFAULT 0')
        await conn.execute('ALTER TABLE preorders ADD COLUMN IF NOT EXISTS invoice REAL DEFAULT 0')
        await conn.execute('ALTER TABLE sales ADD COLUMN IF NOT EXISTS transfer REAL DEFAULT 0')
        await conn.execute('ALTER TABLE sales ADD COLUMN IF NOT EXISTS invoice REAL DEFAULT 0')
        await conn.execute('ALTER TABLE sales ADD COLUMN IF NOT EXISTS message_id BIGINT UNIQUE')
        await conn.execute('ALTER TABLE purchases ALTER COLUMN payment_details TYPE JSONB USING payment_details::jsonb')

        # Колонки брони
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_price FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_prepayment FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_platform VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_full_name VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_phone VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS booking_payment_type VARCHAR')

        # Колонки продажи
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_price FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_prepayment FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_payment_type VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_platform VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_full_name VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_phone VARCHAR')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS sale_payment_amount FLOAT')
        await conn.execute('ALTER TABLE items ADD COLUMN IF NOT EXISTS is_sold BOOLEAN DEFAULT FALSE')

        # Колонки для связи финансов и продажи
        await conn.execute('ALTER TABLE daily_payments ADD COLUMN IF NOT EXISTS sale_message_id BIGINT')
        await conn.execute('ALTER TABLE deleted_items ADD COLUMN IF NOT EXISTS sale_message_id BIGINT')

        # ДОБАВЛЕНО: birth_date в clients
        await conn.execute('ALTER TABLE clients ADD COLUMN IF NOT EXISTS birth_date DATE')

        # Создаём служебную категорию и товар для статистики броней (id=0)
        await conn.execute('''
            INSERT INTO categories (name) VALUES ('__SYSTEM__')
            ON CONFLICT (name) DO NOTHING
        ''')
        sys_cat_id = await conn.fetchval("SELECT id FROM categories WHERE name = '__SYSTEM__'")
        await conn.execute('''
            INSERT INTO items (id, text, category_id, is_booked)
            VALUES (0, '__SYSTEM_STATS__', $1, FALSE)
            ON CONFLICT (id) DO NOTHING
        ''', sys_cat_id)

    logger.info("✅ Инициализация БД завершена (таблицы, индексы и колонки созданы)")


async def check_db_health() -> bool:
    """Проверяет доступность базы данных."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute('SELECT 1')
        return True
    except Exception:
        return False


async def check_redis_health() -> bool:
    """Проверяет доступность Redis (если настроен)."""
    if not config.REDIS_URL:
        return True
    try:
        import redis.asyncio as redis
        r = redis.from_url(config.REDIS_URL, decode_responses=True)
        await r.ping()
        await r.aclose()
        return True
    except Exception:
        return False
