# Файл: web_admin/templates.py
import json
import logging
from datetime import date, datetime

from fastapi.templating import Jinja2Templates

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="web_admin/templates")

def safe_fromjson(value):
    if not value:
        return []
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError, AttributeError):
        logger.warning(f"Ошибка парсинга JSON: {value[:100] if isinstance(value, str) else value}")
        return []

def format_date_filter(value, fmt="%d.%m.%Y"):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime(fmt)
    if isinstance(value, date):
        return value.strftime(fmt)
    if isinstance(value, str):
        for fmt_in in ["%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"]:
            try:
                dt = datetime.strptime(value, fmt_in)
                return dt.strftime(fmt)
            except ValueError:
                continue
    return str(value)

templates.env.filters["fromjson"] = safe_fromjson
templates.env.filters["format_date"] = format_date_filter
