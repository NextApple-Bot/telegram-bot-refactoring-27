"""
Web Admin Routes Package
Предоставляет все submodule роутеров для импорта в web_admin/main.py
(точная совместимость с версией 26/27)
"""

from . import (
    auth,
    clients,
    dashboard,
    debug,
    purchases,
    search,
    sellers,
    sold,
    stats,
)

# Ассортимент (импортируется с алиасами в web_admin/main.py)
from .assortment import views as assortment_views
from .assortment import manage as assortment_manage
from .assortment import booking as assortment_booking

__all__ = [
    "auth",
    "clients",
    "dashboard",
    "debug",
    "purchases",
    "search",
    "sellers",
    "sold",
    "stats",
    "assortment_views",
    "assortment_manage",
    "assortment_booking",
]
