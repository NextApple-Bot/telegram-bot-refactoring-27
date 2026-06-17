import re
from typing import List, Optional


def normalize_serial(serial: str | None) -> Optional[str]:
    """Нормализация серийного номера."""
    if not serial:
        return None
    return re.sub(r'[\s\-]', '', serial).upper()


def extract_serials(text: str) -> List[str]:
    """Извлечение серийных номеров из текста."""
    if not text:
        return []

    pattern = r'\(([A-Z0-9\-]{6,})\)|([A-Z0-9\-]{8,})'
    matches = re.findall(pattern, text, re.IGNORECASE)

    serials = []
    for match in matches:
        serial = match[0] or match[1]
        if serial:
            normalized = normalize_serial(serial)
            if normalized and normalized not in serials:
                serials.append(normalized)
    return serials


def parse_arrival_text(text: str) -> List[dict]:
    """Парсинг текста прибытия."""
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    items = []

    for line in lines:
        serials = extract_serials(line)
        serial = serials[0] if serials else None
        clean_text = re.sub(r'\s*\([A-Z0-9\-]{6,}\)\s*', ' ', line).strip()
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

    # Оставляем только цифры и +
    cleaned = re.sub(r'[^\d+]', '', str(phone).strip())

    if not cleaned:
        return False

    # Приводим российские номера к единому виду
    if cleaned.startswith('+'):
        cleaned = cleaned[1:]
    if cleaned.startswith('8') and len(cleaned) == 11:
        cleaned = '7' + cleaned[1:]

    # Российский номер: 11 цифр, начинается с 7
    if cleaned.startswith('7') and len(cleaned) == 11:
        return True

    # Международный номер: от 10 до 15 цифр
    if 10 <= len(cleaned) <= 15:
        return True

    return False
