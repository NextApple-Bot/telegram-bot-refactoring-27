from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from web_admin.auth import login, logout
from web_admin.templates import templates

router = APIRouter()


@router.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if login(request, password):
        # Правильный редирект (без /admin, потому что приложение смонтировано под /admin)
        return RedirectResponse(url="/dashboard", status_code=303)
    
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})


@router.get("/logout")
async def logout_user(request: Request):
    logout(request)
    # Правильный редирект на логин
    return RedirectResponse(url="/auth/login", status_code=303)
