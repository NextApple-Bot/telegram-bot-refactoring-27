from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from web_admin.auth import login_user, logout_user, is_authenticated
from web_admin.templates import templates

router = APIRouter()


@router.get("/login")
async def login_form(request: Request):
    if is_authenticated(request):
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if login_user(request, password):
        return RedirectResponse(url="/dashboard", status_code=303)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Неверный пароль"})


@router.get("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/auth/login")
