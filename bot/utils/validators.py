import re


def extract_serials(text: str) -> list[str]:
    """Улучшенная версия с защитой от цветов и несерийных слов."""
    if not isinstance(text, str):
        return []

    # Слова, которые точно не являются серийными номерами
    COLOR_WORDS = {
        "BLUE", "YELLOW", "INDIGO", "CITRUS", "LAVENDER", "PURPLE",
        "BLACK", "WHITE", "RED", "GREEN", "ORANGE", "PINK", "GRAY", "GREY",
        "SPACE", "STARLIGHT", "MIDNIGHT", "SILVER", "GOLD", "GRAPHITE"
    }

    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)

    for match in matches:
        candidate = match.group(1).strip()
        if not candidate:
            continue

        upper_candidate = candidate.upper()

        # Пропускаем цвета
        if upper_candidate in COLOR_WORDS:
            continue
        if any(color in upper_candidate for color in COLOR_WORDS):
            continue

        # Вариант с символом №
        if '№' in candidate:
            serials.add(upper_candidate)
            continue

        # Чисто цифровой серийник (≥10 цифр)
        if candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
            continue

        # С дефисом
        if '-' in candidate and re.fullmatch(r'[A-Za-z0-9\-]{6,30}', candidate):
            serials.add(upper_candidate)
            continue

        # Смешанный формат (буквы + цифры) — основной случай
        if re.fullmatch(r'[A-Za-z0-9]{6,30}', candidate):
            if any(char.isdigit() for char in candidate):
                serials.add(upper_candidate)

    return list(serials)


def normalize_serial(serial: str) -> str:
    """Нормализует серийный номер (убирает пробелы и приводит к верхнему регистру)."""
    if not serial:
        return ""
    return re.sub(r'\s+', '', serial).upper()
