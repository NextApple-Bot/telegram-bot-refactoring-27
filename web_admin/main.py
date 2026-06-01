from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.gzip import GZipMiddleware

from web_admin.auth import is_authenticated

from web_admin.routes import auth, clients, dashboard, debug, purchases, sellers, sold, stats
from web_admin.routes.assortment import manage as assortment_manage
from web_admin.routes.assortment import views as assortment_views

app = FastAPI(title="Telegram Bot Admin Panel", redirect_slashes=False)
app.add_middleware(GZipMiddleware, minimum_size=500)

# === Подключаем роуты с правильными префиксами ===
app.include_router(auth.router, prefix="/admin/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/admin/dashboard", tags=["dashboard"])
app.include_router(clients.router, prefix="/admin/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/admin/purchases", tags=["purchases"])
app.include_router(assortment_views.router, prefix="/admin/assortment", tags=["assortment"])
app.include_router(assortment_manage.router, prefix="/admin/assortment", tags=["assortment_manage"])
app.include_router(sold.router, prefix="/admin/sold", tags=["sold"])
app.include_router(stats.router, prefix="/admin/stats", tags=["stats"])
app.include_router(sellers.router, prefix="/admin/sellers", tags=["sellers"])
app.include_router(debug.router, prefix="/admin", tags=["debug"])


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    # Пропускаем страницы логина и статику
    if request.url.path.startswith("/admin/auth/login") or request.url.path.startswith("/admin/static"):
        return await call_next(request)

    if not is_authenticated(request):
        return RedirectResponse(url="/admin/auth/login")

    return await call_next(request)


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")
