from .booking import router as booking_router
from .manage import router as manage_router
from .views import router as views_router

routers = [
    views_router,
    manage_router,
    booking_router,
]
