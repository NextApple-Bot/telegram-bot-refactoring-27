from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.middleware.gzip import GZipMiddleware

from web_admin.auth import is_authenticated
from web_admin.routes import auth, clients, dashboard, debug, purchases, sellers, sold, stats
from web_admin.routes.assortment import manage as assortment_manage
from web_admin.routes.assortment import views as assortment_views

app = FastAPI(title="Telegram Bot Admin Panel")
app.add_middleware(GZipMiddleware, minimum_size=500)

# Роутеры
app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
app.include_router(clients.router, prefix="/clients", tags=["clients"])
app.include_router(purchases.router, prefix="/purchases", tags=["purchases"])
app.include_router(assortment_views.router, prefix="/assortment", tags=["assortment"])
app.include_router(assortment_manage.router, prefix="/assortment", tags=["assortment_manage"])
app.include_router(sold.router, prefix="/sold", tags=["sold"])
app.include_router(stats.router, prefix="/stats", tags=["stats"])
app.include_router(sellers.router, prefix="/sellers", tags=["sellers"])
app.include_router(debug.router, prefix="/admin", tags=["debug"])


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/auth/login"):
        return await call_next(request)
    if not is_authenticated(request):
        return RedirectResponse(url="/auth/login")
    return await call_next(request)


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


# ==================== ВРЕМЕННЫЙ ДИАГНОСТИЧЕСКИЙ ЭНДПОИНТ ====================
@app.get("/debug/routes")
async def debug_routes():
    routes = []
    for route in app.routes:
        routes.append({
            "path": getattr(route, "path", str(route)),
            "methods": getattr(route, "methods", None),
            "name": getattr(route, "name", None),
        })
    return JSONResponse(routes)
