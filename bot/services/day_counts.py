"""Извлечение счётчиков дня (продажи / предзаказы / брони) из текста итогов."""
from __future__ import annotations

import re

_COUNT_LINE_PATTERNS: dict[str, re.Pattern[str]] = {
    "sales_count": re.compile(
        r"(?:продаж[аи]?|продано|sales?)[ \t]*[:\-—]?[ \t]*(\d{1,4})\b"
        r"|(\d{1,4})[ \t]*(?:продаж[аи]?|продано)\b",
        re.IGNORECASE,
    ),
    "preorders_count": re.compile(
        r"(?:предзаказ(?:ы|ов|а)?|pre-?orders?)[ \t]*[:\-—]?[ \t]*(\d{1,4})\b"
        r"|(\d{1,4})[ \t]*(?:предзаказ(?:ы|ов|а)?)\b",
        re.IGNORECASE,
    ),
    "bookings_count": re.compile(
        r"(?:брон(?:ь|и|ей)|bookings?)(?![ \t]*от)[ \t]*[:\-—]?[ \t]*(\d{1,4})\b"
        r"|(\d{1,4})[ \t]*(?:брон(?:ь|и|ей))\b",
        re.IGNORECASE,
    ),
}

# «План продаж 30», «План: 25» — не факт, пропускаем
_PLAN_LINE = re.compile(r"план", re.IGNORECASE)


def extract_day_counts(text: str) -> dict[str, int | None]:
    """
    Достаёт из текста итогов: продажи / предзаказы / брони (шт.).
    None — если в тексте не найдено. Берёт последнее совпадение по типу (построчно).
    Строки с «план» не учитываются.
    """
    result: dict[str, int | None] = {
        "sales_count": None,
        "preorders_count": None,
        "bookings_count": None,
    }
    if not (text or "").strip():
        return result

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if _PLAN_LINE.search(line):
            continue
        for key, pattern in _COUNT_LINE_PATTERNS.items():
            m = pattern.search(line)
            if not m:
                continue
            raw = m.group(1) or m.group(2)
            if raw is None:
                continue
            try:
                n = int(raw)
            except ValueError:
                continue
            if 0 <= n <= 9999:
                result[key] = n
    return result
