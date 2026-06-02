from passlib.context import CryptContext
from starlette.requests import Request

from bot import config

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password: str) -> bool:
    if config.ADMIN_PASSWORD and plain_password == config.ADMIN_PASSWORD:
        return True
    if config.ADMIN_PASSWORD_HASH:
        return pwd_context.verify(plain_password, config.ADMIN_PASSWORD_HASH)
    return False

def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated", False)

def login(request: Request, password: str) -> bool:
    if verify_password(password):
        request.session["authenticated"] = True
        return True
    return False

def logout(request: Request) -> None:
    request.session.clear()
