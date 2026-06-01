from datetime import datetime, timedelta
from starlette.requests import Request

from bot.config import config


def verify_password(plain_password: str) -> bool:
    """Проверяет пароль."""
    if not config.ADMIN_PASSWORD:
        return False
    return plain_password == config.ADMIN_PASSWORD


def is_authenticated(request: Request) -> bool:
    """Проверяет авторизацию. Более устойчивая версия."""
    try:
        # Пытаемся получить сессию разными способами
        session = getattr(request, 'session', None)
        if session is None:
            # Пробуем через scope
            scope = getattr(request, 'scope', {})
            session = scope.get('session', {})

        if not session or not session.get("authenticated"):
            return False

        login_time_str = session.get("login_time")
        if login_time_str:
            try:
                login_time = datetime.fromisoformat(login_time_str)
                if datetime.utcnow() - login_time > timedelta(days=7):
                    session.clear()
                    return False
            except Exception:
                if hasattr(session, 'clear'):
                    session.clear()
                return False

        return True
    except Exception:
        return False


def login_user(request: Request, password: str) -> bool:
    """Выполняет вход."""
    if verify_password(password):
        try:
            request.session["authenticated"] = True
            request.session["login_time"] = datetime.utcnow().isoformat()
            return True
        except Exception:
            return False
    return False


def logout_user(request: Request):
    """Выход из системы."""
    try:
        request.session.clear()
    except Exception:
        pass
