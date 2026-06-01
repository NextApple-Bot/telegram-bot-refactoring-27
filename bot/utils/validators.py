import re

# Список слов, которые точно не являются серийными номерами
COLOR_WORDS = {
    "BLUE", "YELLOW", "INDIGO", "CITRUS", "LAVENDER", "PURPLE", 
    "BLACK", "WHITE", "RED", "GREEN", "ORANGE", "PINK", "GRAY", "GREY",
    "SPACE", "STARLIGHT", "MIDNIGHT", "SILVER", "GOLD", "GRAPHITE"
}

def extract_serials(text: str) -> list[str]:
    if not isinstance(text, str):
        return []

    serials = set()
    matches = re.finditer(r'\(([^)]+)\)', text)

    for match in matches:
        candidate = match.group(1).strip()
        if not candidate:
            continue

        upper_candidate = candidate.upper()

        # Пропускаем явные цвета и несерийные слова
        if upper_candidate in COLOR_WORDS:
            continue
        if any(color in upper_candidate for color in COLOR_WORDS):
            continue

        # Вариант 1: содержит символ №
        if '№' in candidate:
            serials.add(upper_candidate)
            continue

        # Вариант 2: чисто цифровой серийник (минимум 10 цифр)
        if candidate.isdigit() and len(candidate) >= 10:
            serials.add(candidate)
            continue

        # Вариант 3: содержит дефис (типичный формат Apple)
        if '-' in candidate and re.fullmatch(r'[A-Za-z0-9\-]{6,30}', candidate):
            serials.add(upper_candidate)
            continue

        # Вариант 4: смешанный (буквы + цифры) — самый частый случай
        # Требуем минимум 6 символов и наличие хотя бы одной цифры
        if re.fullmatch(r'[A-Za-z0-9]{6,30}', candidate):
            if any(char.isdigit() for char in candidate):   # обязательно должна быть цифра
                serials.add(upper_candidate)

    return list(serials)
