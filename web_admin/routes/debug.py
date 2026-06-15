from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/")
async def debug_info(request: Request):
    """Простая debug-информация."""
    return {
        "status": "ok",
        "message": "Debug endpoint is working",
        "path": str(request.url),
    }


@router.get("/routes")
async def debug_routes(request: Request):
    """Выводит список всех зарегистрированных роутов (удобно для отладки)."""
    from main import app  # Импортируем основное приложение

    routes_info = []
    for route in app.routes:
        routes_info.append({
            "path": getattr(route, "path", str(route)),
            "methods": list(getattr(route, "methods", [])) if hasattr(route, "methods") else None,
            "name": getattr(route, "name", None),
        })

    return JSONResponse(routes_info)
