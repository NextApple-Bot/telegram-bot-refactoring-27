import logging

from sqlalchemy import func, select
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
    async def add_item(
        text: str,
        serial: str | None = None,
        category_id: int | None = None,
        category_name: str | None = None
    ):
        """Добавляет товар. Можно указать category_id или category_name."""
        if category_id is None:
            if category_name is None:
                category_name = "Общее:"
            cat_id = await ItemRepository.get_or_create_category(category_name)
        else:
            cat_id = category_id

        normalized_serial = serial.strip().upper() if serial else None
        is_booked = 'Бронь от' in text

        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            new_item = Item(
                text=text,
                serial=normalized_serial,
                category_id=cat_id,
                is_booked=is_booked
            )
            session.add(new_item)
            logger.info(f"✅ Товар добавлен: {text[:50]}")

    @staticmethod
    async def get_item_id_by_serial(serial: str, conn=None) -> int | None:
        if not serial:
            return None
        normalized = serial.strip().upper()
        async def _impl(session):
            result = await session.execute(
                select(Item.id).where(func.upper(Item.serial) == normalized)
            )
            return result.scalar_one_or_none()
        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session:
                return await _impl(session)

    @staticmethod
    async def get_item_by_serial(serial: str, conn=None) -> dict | None:
        normalized = serial.strip().upper()
        async def _impl(session):
            result = await session.execute(
                select(Item.id, Item.text, Category.id.label('category_id'), Category.name.label('category_name'))
                .join(Category, Item.category_id == Category.id)
                .where(func.upper(Item.serial) == normalized)
            )
            row = result.mappings().one_or_none()
            return dict(row) if row else None
        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session:
                return await _impl(session)

    @staticmethod
    async def get_item_by_text(text: str, conn=None) -> dict | None:
        async def _impl(session):
            result = await session.execute(
                select(Item.id, Item.text, Category.name.label('category_name'))
                .join(Category, Item.category_id == Category.id)
                .where(Item.text == text)
            )
            row = result.mappings().one_or_none()
            return dict(row) if row else None
        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session:
                return await _impl(session)

    @staticmethod
    async def remove_item_by_serial(serial: str, conn=None) -> int:
        normalized = serial.strip().upper() if serial else None
        async def _impl(session):
            result = await session.execute(
                select(Item.id).where(func.upper(Item.serial) == normalized)
            )
            item_id = result.scalar_one_or_none()
            if item_id:
                item = await session.get(Item, item_id)
                if item:
                    await session.delete(item)
                    await session.flush()
                    return 1
            return 0
        if conn is not None:
            return await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                return await _impl(session)

    @staticmethod
    async def add_deleted_item(
        item_id: int,
        text: str,
        serial: str,
        category_id: int,
        reason: str = 'manual',
        conn=None
    ):
        async def _impl(session):
            deleted = DeletedItem(
                item_id=item_id,
                text=text,
                serial=serial,
                category_id=category_id,
                reason=reason
            )
            session.add(deleted)
            await session.flush()
        if conn is not None:
            await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                await _impl(session)

    @staticmethod
    async def get_last_deleted_item() -> dict | None:
        async_session = get_async_session_factory()
        async with async_session() as session:
            result = await session.execute(
                select(DeletedItem)
                .where(~DeletedItem.restored)
                .order_by(DeletedItem.deleted_at.desc())
                .limit(1)
            )
            item = result.scalar_one_or_none()
            if not item:
                return None
            return {
                "id": item.id,
                "item_id": item.item_id,
                "text": item.text,
                "serial": item.serial,
                "category_id": item.category_id,
                "deleted_at": item.deleted_at,
                "restored": item.restored,
                "reason": item.reason,
                "sale_message_id": item.sale_message_id
            }

    @staticmethod
    async def restore_deleted_item(deleted_id: int) -> bool:
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            item = await session.get(DeletedItem, deleted_id)
            if item:
                item.restored = True
                return True
            return False

    @staticmethod
    async def mark_item_booked(item_id: int, book_text: str, conn=None):
        async def _impl(session):
            item = await session.get(Item, item_id)
            if item:
                item.text = book_text
                item.is_booked = True
                session.add(item)
                await session.flush()
        if conn is not None:
            await _impl(conn)
        else:
            async_session = get_async_session_factory()
            async with async_session() as session, session.begin():
                await _impl(session)

    @staticmethod
    async def get_all_categories_with_items():
        """Возвращает категории с товарами, отсортированные по sort_order, затем по имени."""
        async_session = get_async_session_factory()
        async with async_session() as session:
            result = await session.execute(
                select(Category.name, Item.text)
                .outerjoin(Item, Category.id == Item.category_id)
                .where(Category.name != '__SYSTEM__')
                .order_by(Category.sort_order, Category.name, Item.id)
            )
            rows = result.all()
            categories_dict = {}
            for row in rows:
                cat_name = row.name
                if cat_name not in categories_dict:
                    categories_dict[cat_name] = []
                if row.text:
                    categories_dict[cat_name].append(row.text)
            return [{"header": cat, "items": items} for cat, items in categories_dict.items()]

    @staticmethod
    async def get_all_items_serials():
        """Возвращает список всех серийников и текстов товаров."""
        async_session = get_async_session_factory()
        async with async_session() as session:
            result = await session.execute(
                select(Item.text, Item.serial)
            )
            rows = result.all()
            return [{"text": row.text, "serial": row.serial} for row in rows]

    @staticmethod
    async def bulk_replace_assortment(categories: list[dict[str, list[str]]]) -> None:
        """Полностью заменяет ассортимент новыми категориями и товарами."""
        from bot.services.cache import cache
        async_session = get_async_session_factory()
        async with async_session() as session, session.begin():
            # Очистка старых данных
            await session.execute(select(Item).where(Item.category_id.notin_(
                select(Category.id).where(Category.name == '__SYSTEM__')
            )))
            items_to_delete = await session.execute(select(Item).where(Item.category_id.notin_(
                select(Category.id).where(Category.name == '__SYSTEM__')
            )))
            for item in items_to_delete.scalars():
                await session.delete(item)
            await session.flush()

            cats_to_delete = await session.execute(
                select(Category).where(Category.name != '__SYSTEM__')
            )
            for cat in cats_to_delete.scalars():
                await session.delete(cat)
            await session.flush()

            # Вставка новых категорий и товаров
            for idx, cat_data in enumerate(categories):
                new_cat = Category(name=cat_data['header'], sort_order=idx)
                session.add(new_cat)
                await session.flush()
                for item_text in cat_data['items']:
                    serials = extract_serials(item_text)
                    serial = serials[0].strip().upper() if serials else None
                    is_booked = 'Бронь от' in item_text
                    new_item = Item(
                        text=item_text,
                        serial=serial,
                        category_id=new_cat.id,
                        is_booked=is_booked
                    )
                    session.add(new_item)
        await cache.delete("assortment:all")
        logger.info(f"Ассортимент полностью заменён ({len(categories)} категорий)")
