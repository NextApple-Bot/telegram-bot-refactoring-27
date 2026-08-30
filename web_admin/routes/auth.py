from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from web_admin.auth import login, logout
from web_admin.services.audit import log_admin_action
from web_admin.templates import templates

router = APIRouter()


@router.get("/login")
async def login_form(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_submit(request: Request, password: str = Form(...)):
    if login(request, password):
        await log_admin_action("login_ok", request=request)
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    await log_admin_action("login_fail", request=request)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Неверный пароль"}
    )


@router.get("/logout")
async def logout_user(request: Request):
    await log_admin_action("logout", request=request)
    logout(request)
    return RedirectResponse(url="/admin/auth/login", status_code=303)
