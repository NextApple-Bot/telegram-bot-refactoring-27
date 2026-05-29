# Пакет для роутов ассортимента
from .booking import router as booking_router
from .manage import router as manage_router
from .sales import router as sales_router
from .views import router as views_router

routers = [views_router, manage_router, booking_router, sales_router]
