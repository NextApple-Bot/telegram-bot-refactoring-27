# Пакет роутов ассортимента
from .booking import router as booking_router
from .manage import router as manage_router
from .views import router as views_router

# sales.py не экспортирует router (там только функции),
# поэтому его здесь не подключаем как отдельный роутер

routers = [
    views_router,
    manage_router,
    booking_router,
]
