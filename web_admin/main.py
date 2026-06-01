from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.gzip import GZipMiddleware

from web_admin.auth import is_authenticated

# Роутеры
from web_admin.routes import (
    auth as auth_router,
    clients as clients_router,
    dashboard as dashboard_router,
    debug as debug_router,
    purchases as purchases_router,
    sellers as sellers_router,
    sold as sold_router,
    stats as stats_router,
)
from web_admin.routes.assortment import manage as assortment_manage_router
from web_admin.routes.assortment import views as assortment_views_router

app = FastAPI(title="Telegram Bot Admin Panel", redirect_slashes=False)
app.add_middleware(GZipMiddleware, minimum_size=500)

# === Подключаем роуты ===
app.include_router(auth_router.router,          prefix="/admin/auth",      tags=["auth"])
app.include_router(dashboard_router.router,     prefix="/admin/dashboard", tags=["dashboard"])
app.include_router(clients_router.router,       prefix="/admin/clients",   tags=["clients"])
app.include_router(purchases_router.router,     prefix="/admin/purchases", tags=["purchases"])
app.include_router(assortment_views_router.router, prefix="/admin/assortment", tags=["assortment"])
app.include_router(assortment_manage_router.router, prefix="/admin/assortment", tags=["assortment_manage"])
app.include_router(sold_router.router,          prefix="/admin/sold",      tags=["sold"])
app.include_router(stats_router.router,         prefix="/admin/stats",     tags=["stats"])
app.include_router(sellers_router.router,       prefix="/admin/sellers",   tags=["sellers"])
app.include_router(debug_router.router,         prefix="/admin",           tags=["debug"])


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/admin/auth/login"):
        return await call_next(request)

    if not is_authenticated(request):
        return RedirectResponse(url="/admin/auth/login")

    return await call_next(request)


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")
