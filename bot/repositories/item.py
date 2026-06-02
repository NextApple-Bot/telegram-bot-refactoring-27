import logging

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from bot.db import get_async_session_factory
from bot.models import Category, DeletedItem, Item
from bot.utils.validators import extract_serials

logger = logging.getLogger(__name__)


class ItemRepository:
    """Репозиторий для работы с товарами и категориями (SQLAlchemy 2.0)."""

    @staticmethod
    async def get_or_create_category(name: str, conn=None) -> int:
        """Возвращает ID категории по имени, создаёт при отсутствии."""
        norm_name = name.lower().rstrip(':')
        async def _impl(session):
            # Ищем категорию
            result = await session.execute(
                select(Category.id).where(func.lower(Category.name) == norm_name)
            )
            cat_id = result.scalar_one_or_none()
            if cat_id:
                return cat_id
            # Создаём новую
            max_order = await session.execute(
                select(func.coalesce(func.max(Category.sort_order), -1))
            )
            new_order = max_order.scalar() + 1
            new_cat = Category(name=name, sort_order=new_order)
            session.add(new_cat)
            try:
                await session.flush()
                return new_cat.id
            except IntegrityError:
                # Категория была создана между select и insert
                await session.rollback()
                result = await session.execute(
                    select(Category.id).where(Category.name == name)
                )
                existing = result.scalar_one()
                return existing.id

        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                return await _impl(session)

    @staticmethod
    async def bulk_replace_assortment(categories: list[dict], conn=None) -> None:
        """Полная атомарная замена всего ассортимента."""
        from bot.services.cache import cache

        if not categories:
            logger.warning("bulk_replace_assortment вызван с пустым списком категорий")
            return

        own_session = False
        if conn is None:
            async_session = get_async_session_factory()
            session = async_session()
            own_session = True
        else:
            session = conn

        try:
            if own_session:
                await session.begin()

            # Получаем ID системной категории
            sys_result = await session.execute(
                select(Category.id).where(Category.name == '__SYSTEM__')
            )
            sys_id = sys_result.scalar_one_or_none()

            # Удаляем все товары кроме системных
            if sys_id:
                await session.execute(delete(Item).where(Item.category_id != sys_id))
            else:
                await session.execute(delete(Item))

            # Удаляем все категории кроме системной
            await session.execute(delete(Category).where(Category.name != '__SYSTEM__'))

            await session.flush()

            # Вставляем новые категории и товары
            for idx, cat_data in enumerate(categories):
                cat_name = cat_data.get('header') or cat_data.get('name', 'Без категории')
                cat_id = await ItemRepository.get_or_create_category(cat_name, conn=session)

                for item_text in cat_data.get('items', []):
                    if not item_text or not item_text.strip():
                        continue

                    serials = extract_serials(item_text)
                    serial = serials[0].strip().upper() if serials else None
                    is_booked = 'Бронь от' in item_text

                    new_item = Item(
                        text=item_text,
                        serial=serial,
                        category_id=cat_id,
                        is_booked=is_booked
                    )
                    session.add(new_item)

            if own_session:
                await session.commit()

            await cache.delete("assortment:all")
            total_items = sum(len(cat.get('items', [])) for cat in categories)
            logger.info(
                f"✅ Ассортимент полностью заменён: "
                f"{len(categories)} категорий, {total_items} товаров"
            )

        except Exception as e:
            if own_session:
                await session.rollback()
            logger.exception("❌ Критическая ошибка при bulk_replace_assortment")
            raise
        finally:
            if own_session:
                await session.close()

    # === Остальной код файла (все остальные методы) остаётся без изменений ===
    # (add_item, get_item_id_by_serial, get_all_categories_with_items и т.д.)
    # Я не менял их, чтобы не ломать ничего.
