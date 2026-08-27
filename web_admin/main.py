import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.sessions import SessionMiddleware

from web_admin.auth import is_authenticated

from web_admin.routes import (
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

from web_admin.routes.assortment import manage as assortment_manage
from web_admin.routes.assortment import views as assortment_views
from web_admin.routes.assortment import sales as assortment_sales
from web_admin.routes.assortment import booking as assortment_booking

app = FastAPI(title="Telegram Bot Admin Panel")
app.add_middleware(GZipMiddleware, minimum_size=500)

# Сессия нужна и на смонтированном приложении:
# родительский SessionMiddleware иногда не прокидывает session в mount.
_secret = os.getenv("SECRET_KEY") or "change-me-in-production"
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret,
    max_age=3600 * 24 * 7,
    same_site="lax",
    https_only=False,
)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(search.router, prefix="/search", tags=["search"])
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/purchases", tags=["purchases"])

app.include_router(assortment_views.router, prefix="/assortment", tags=["assortment"])
app.include_router(assortment_manage.router, prefix="/assortment", tags=["assortment_manage"])
app.include_router(assortment_sales.router, prefix="/assortment", tags=["assortment_sales"])
app.include_router(assortment_booking.router, prefix="/assortment", tags=["assortment_booking"])

app.include_router(sold.router, prefix="/sold", tags=["sold"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
app.include_router(debug.router, prefix="/debug", tags=["debug"])


def _is_public_path(path: str) -> bool:
    """
    При mount('/admin', app) path внутри FastAPI = /auth/login, /dashboard/...
    Снаружи браузер видит /admin/auth/login. Проверяем оба варианта.
    """
    public_prefixes = (
        "/auth/login",
        "/admin/auth/login",
        "/static",
        "/admin/static",
    )
    return any(path == p or path.startswith(p + "/") or path.startswith(p + "?") for p in public_prefixes) or path in public_prefixes


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path or ""
    if _is_public_path(path):
        return await call_next(request)

    if not is_authenticated(request):
        # Для API/fetch — JSON 401 вместо HTML-редиректа (иначе «Ошибка соединения»)
        accept = (request.headers.get("accept") or "").lower()
        is_api = (
            request.method in ("POST", "PUT", "PATCH", "DELETE")
            or "application/json" in accept
            or path.rstrip("/").endswith(
                ("/update_stats", "/toggle_seller_day", "/top_models_data", "/search/api")
            )
            or "/search/api" in path
        )
        if is_api:
            return JSONResponse(
                {"success": False, "error": "Не авторизован. Обновите страницу и войдите снова."},
                status_code=401,
            )
        return RedirectResponse(url="/admin/auth/login")

    return await call_next(request)


@app.get("/")
async def root():
    return RedirectResponse(url="/admin/dashboard")
