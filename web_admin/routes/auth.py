from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from web_admin.auth import is_authenticated, login_user, logout_user

router = APIRouter()
templates = Jinja2Templates(directory="web_admin/templates")


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if is_authenticated(request):
        return RedirectResponse("/admin/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@router.post("/login")
async def login_post(request: Request, password: str = Form(...)):
    if login_user(request, password):
        return RedirectResponse("/admin/dashboard", status_code=303)
    else:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Неверный пароль"}
        )


@router.get("/logout")
async def logout(request: Request):
    logout_user(request)
    return RedirectResponse("/admin/auth/login")
