# bot/repositories/__init__.py

# Не импортируем ItemRepository здесь на верхнем уровне,
# чтобы избежать циклических импортов.
# Импортируй напрямую: from bot.repositories.item import ItemRepository

from .client import ClientRepository
from .stats import StatsRepository

__all__ = [
    "ClientRepository",
    "StatsRepository",
]
