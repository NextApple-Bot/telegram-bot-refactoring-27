import re
from typing import List, Optional


def normalize_serial(serial: str | None) -> Optional[str]:
    """Нормализация серийного номера."""
    if not serial:
        return None
    return re.sub(r'[\s\-]', '', serial).upper()


def _looks_like_phone(value: str) -> bool:
    """
    Определяет, похожа ли строка на телефонный номер.
    Не считаем серийником чистые цифровые последовательности
    длиной 10–15 символов (типичные телефоны).
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
    Извлечение серийных номеров из текста.

    Серийник считается ТОЛЬКО если он в скобках:
    - круглые: (CFW0KXY231)
    - квадратные: [CFW0KXY231]

    Без скобок серийники не ищутся.
    Номера телефонов игнорируются.
    """
    if not text:
        return []

    # Только содержимое скобок () или []
    pattern = r'[\(\[]([A-Za-z0-9\-]{6,})[\)\]]'
    matches = re.findall(pattern, text)

    serials: List[str] = []
    for serial in matches:
        if not serial:
            continue

        normalized = normalize_serial(serial)
        if not normalized:
            continue

        # Пропускаем телефоны
        if _looks_like_phone(normalized):
            continue

        if normalized not in serials:
            serials.append(normalized)

    return serials


def extract_primary_serial(text: str) -> Optional[str]:
    """
    Для одной строки товара выбирает основной серийник.

    Если в строке несколько кодов в скобках, например:
      PlayStation 5 (CFI-2118) (S01-E55B01CL410256288)
    берём самый длинный — это реальный серийник устройства,
    а не код модели (CFI-2118).
    """
    serials = extract_serials(text)
    if not serials:
        return None
    return max(serials, key=len)


def parse_arrival_text(text: str) -> List[dict]:
    """Парсинг текста прибытия."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    items = []

    for line in lines:
        serial = extract_primary_serial(line)
        clean_text = re.sub(r'\s*[\(\[][A-Za-z0-9\-]{6,}[\)\]]\s*', ' ', line).strip()
        if clean_text:
            items.append({"text": clean_text, "serial": serial})
    return items


def validate_phone(phone: str | None) -> bool:
    """
    Валидация телефона (российские и международные номера).
    Принимает номера с +, 7, 8, пробелами, скобками, дефисами.
    Возвращает True, если номер выглядит корректно.
    """
    if not phone:
        return True  # пустой телефон считаем допустимым (поле необязательное)

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
