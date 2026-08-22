import re
from typing import List, Optional


def normalize_serial(serial: str | None) -> Optional[str]:
    """Нормализация серийного номера."""
    if not serial:
        return None
    # Сохраняем № для кодов вида №8 / S№10
    s = serial.strip()
    s = re.sub(r'[\s\-]', '', s)
    # Приводим латиницу к upper, № оставляем
    return s.upper().replace('№', '№')


def _looks_like_phone(value: str) -> bool:
    """
    Определяет, похожа ли строка на телефонный номер.
    """
    if not value:
        return False
    digits_only = re.sub(r'\D', '', value)
    if not digits_only.isdigit():
        return False
    if 10 <= len(digits_only) <= 15:
        return True
    return False


def extract_serials(text: str) -> List[str]:
    """
    Извлечение серийных номеров / внутренних кодов из текста.

    Поддерживает:
    - (CFW0KXY231) / [CFW0KXY231] — длинные серийники
    - (№8) / (S№10) / (№1) — внутренние номера аксессуаров
    """
    if not text:
        return []

    serials: List[str] = []

    # 1) Длинные alphanumeric в скобках (от 6 символов)
    for m in re.findall(r'[\(\[]([A-Za-z0-9\-]{6,})[\)\]]', text):
        normalized = normalize_serial(m)
        if normalized and not _looks_like_phone(normalized) and normalized not in serials:
            serials.append(normalized)

    # 2) Внутренние коды: (№8), (S№10), (№ 4)
    for m in re.findall(r'[\(\[](S?№\s*\d+)[\)\]]', text, flags=re.IGNORECASE):
        # Нормализация: S№10 / №8
        code = re.sub(r'\s+', '', m).upper()
        # upper() может испортить № в некоторых локалях — фиксируем
        code = code.replace('Nº', '№').replace('N°', '№')
        if '№' not in code and 'S' in code.upper():
            # fallback если № потерялся
            digits = re.search(r'\d+', m)
            if digits:
                prefix = 'S' if m.upper().startswith('S') else ''
                code = f"{prefix}№{digits.group()}"
        if code and code not in serials:
            serials.append(code)

    return serials


def extract_primary_serial(text: str) -> Optional[str]:
    """
    Для одной строки товара выбирает основной серийник.

    Приоритет:
    1) Самый длинный alphanumeric-код (реальный S/N)
    2) Иначе код вида №8 / S№10
    """
    serials = extract_serials(text)
    if not serials:
        return None

    # Сначала длинные (без №)
    long_ones = [s for s in serials if '№' not in s]
    if long_ones:
        return max(long_ones, key=len)

    return serials[0]


def parse_arrival_text(text: str) -> List[dict]:
    """Парсинг текста прибытия."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    items = []

    for line in lines:
        serial = extract_primary_serial(line)
        clean_text = re.sub(r'\s*[\(\[][A-Za-z0-9№\-\s]{2,}[\)\]]\s*', ' ', line).strip()
        if clean_text:
            items.append({"text": clean_text, "serial": serial})
    return items


def validate_phone(phone: str | None) -> bool:
    """
    Валидация телефона (российские и международные номера).
    """
    if not phone:
        return True

    cleaned = re.sub(r'[^\d+]', '', str(phone).strip())

    if not cleaned:
        return False

    if cleaned.startswith('+'):
        cleaned = cleaned[1:]
    if cleaned.startswith('8') and len(cleaned) == 11:
        cleaned = '7' + cleaned[1:]

    if cleaned.startswith('7') and len(cleaned) == 11:
        return True

    if 10 <= len(cleaned) <= 15:
        return True

    return False
