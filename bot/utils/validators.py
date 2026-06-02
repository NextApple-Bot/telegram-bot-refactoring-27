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
