import re
from typing import List, Optional


def normalize_serial(serial: str | None) -> Optional[str]:
    """Нормализация серийного номера (убирает пробелы, приводит к верхнему регистру)."""
    if not serial:
        return None
    return serial.strip().upper().replace(" ", "").replace("-", "")


def extract_serials(text: str) -> List[str]:
    """
    Извлекает серийные номера из текста.
    Ищет паттерны типа: (ABC123), W42VYXRV96, FFXGQJHF0F11 и т.д.
    """
    if not text:
        return []

    # Ищем серийные номера в скобках или standalone
    pattern = r'\(([A-Z0-9]{8,})\)|([A-Z0-9]{8,})'
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
    """
    Парсит текст прибытия товаров.
    Возвращает список словарей с text и serial.
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    items = []

    for line in lines:
        serials = extract_serials(line)
        serial = serials[0] if serials else None

        # Убираем серийный номер из текста
        clean_text = re.sub(r'\s*\([A-Z0-9]{8,}\)\s*', ' ', line, flags=re.IGNORECASE).strip()
        clean_text = re.sub(r'\s+[A-Z0-9]{8,}\s*$', '', clean_text).strip()

        if clean_text:
            items.append({
                "text": clean_text,
                "serial": serial
            })

    return items
