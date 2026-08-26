import re
from typing import List, Optional


def normalize_serial(serial: str | None) -> Optional[str]:
    """Нормализация серийного номера."""
    if not serial:
        return None
    s = serial.strip()
    s = re.sub(r"[\s\-]", "", s)
    return s.upper().replace("№", "№")


def _looks_like_phone(value: str) -> bool:
    """
    Телефон vs серийник/IMEI.

    Телефон:
      - 11 цифр, начинается с 7 или 8 (РФ)
      - 10 цифр, начинается с 9 (мобильный без кода страны)

    НЕ телефон:
      - 15 цифр (IMEI / Samsung SN вроде 353708650084552)
      - смешанные буквы+цифры
      - короче 10 или длиннее 15
    """
    if not value:
        return False
    digits_only = re.sub(r"\D", "", value)
    if not digits_only.isdigit():
        return False
    # Есть буквы в исходном значении — это серийник
    if re.search(r"[A-Za-zА-Яа-я]", value):
        return False
    n = len(digits_only)
    if n == 11 and digits_only[0] in "78":
        return True
    if n == 10 and digits_only[0] == "9":
        return True
    return False


def extract_serials(text: str) -> List[str]:
    """
    Извлечение серийных номеров / внутренних кодов из текста.

    Поддерживает:
    - (CFW0KXY231) / [CFW0KXY231]
    - (353708650084552) — IMEI / числовой SN (15 цифр)
    - (№8) / (S№10) / (№1)
    """
    if not text:
        return []

    serials: List[str] = []

    # 1) alphanumeric / numeric в скобках (от 6 символов)
    for m in re.findall(r"[\(\[]([A-Za-z0-9\-]{6,})[\)\]]", text):
        normalized = normalize_serial(m)
        if not normalized:
            continue
        if _looks_like_phone(normalized):
            continue
        if normalized not in serials:
            serials.append(normalized)

    # 2) Внутренние коды: (№8), (S№10), (№ 4)
    for m in re.findall(r"[\(\[](S?№\s*\d+)[\)\]]", text, flags=re.IGNORECASE):
        code = re.sub(r"\s+", "", m).upper()
        code = code.replace("Nº", "№").replace("N°", "№")
        if "№" not in code:
            digits = re.search(r"\d+", m)
            if digits:
                prefix = "S" if m.upper().startswith("S") else ""
                code = f"{prefix}№{digits.group()}"
        if code and code not in serials:
            serials.append(code)

    return serials


def extract_primary_serial(text: str) -> Optional[str]:
    """
    Основной серийник строки товара.
    Приоритет: самый длинный alphanumeric, иначе №-код.
    """
    serials = extract_serials(text)
    if not serials:
        return None

    long_ones = [s for s in serials if "№" not in s]
    if long_ones:
        return max(long_ones, key=len)

    return serials[0]


def parse_arrival_text(text: str) -> List[dict]:
    """Парсинг текста прибытия."""
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    items = []

    for line in lines:
        serial = extract_primary_serial(line)
        clean_text = re.sub(
            r"\s*[\(\[][A-Za-z0-9№\-\s]{2,}[\)\]]\s*", " ", line
        ).strip()
        if clean_text:
            items.append({"text": clean_text, "serial": serial})
    return items


def validate_phone(phone: str | None) -> bool:
    """Валидация телефона (российские и международные)."""
    if not phone:
        return True

    cleaned = re.sub(r"[^\d+]", "", str(phone).strip())

    if not cleaned:
        return False

    if cleaned.startswith("+"):
        cleaned = cleaned[1:]
    if cleaned.startswith("8") and len(cleaned) == 11:
        cleaned = "7" + cleaned[1:]

    if cleaned.startswith("7") and len(cleaned) == 11:
        return True

    if 10 <= len(cleaned) <= 15:
        return True

    return False
