"""
Разбор SKU-атрибутов из текста товара (без отдельных колонок в БД).

Память: 128GB / 256 GB / 1TB / 512ГБ
SIM:    SIM+eSIM / eSIM / nano-SIM / dual SIM
Цвет:   словарь популярных EN/RU названий + эвристика «слово перед GB»
"""
from __future__ import annotations

import re
from typing import Any

# Память: 128GB, 256 GB, 1TB, 512ГБ, 1 ТБ
_MEMORY_RE = re.compile(
    r"\b(\d{1,4})\s*(?:GB|GБ|ГБ|Tb|TB|TБ|ТБ)\b",
    re.IGNORECASE,
)

# SIM варианты (порядок важен: сначала составные)
_SIM_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "SIM+eSIM",
        re.compile(
            r"SIM\s*\+\s*e?SIM|SIM\s*&\s*e?SIM|dual\s*sim\s*\+\s*esim",
            re.IGNORECASE,
        ),
    ),
    ("eSIM", re.compile(r"\be\s*-?\s*SIM\b", re.IGNORECASE)),
    ("nano-SIM", re.compile(r"nano\s*-?\s*SIM", re.IGNORECASE)),
    ("Dual SIM", re.compile(r"dual\s*-?\s*SIM", re.IGNORECASE)),
    ("SIM", re.compile(r"\bSIM\b", re.IGNORECASE)),
]

# Популярные цвета (длинные фразы первыми)
_COLOR_PHRASES: list[tuple[str, re.Pattern[str]]] = [
    ("Natural Titanium", re.compile(r"natural\s*titanium|натуральный\s*титан", re.I)),
    ("Blue Titanium", re.compile(r"blue\s*titanium|синий\s*титан", re.I)),
    ("White Titanium", re.compile(r"white\s*titanium|белый\s*титан", re.I)),
    ("Black Titanium", re.compile(r"black\s*titanium|чёрный\s*титан|черный\s*титан", re.I)),
    ("Desert Titanium", re.compile(r"desert\s*titanium|пустынный\s*титан", re.I)),
    ("Space Black", re.compile(r"space\s*black|космический\s*чёрный|космический\s*черный", re.I)),
    ("Space Gray", re.compile(r"space\s*gr[ae]y|серый\s*космос", re.I)),
    ("Sierra Blue", re.compile(r"sierra\s*blue", re.I)),
    ("Pacific Blue", re.compile(r"pacific\s*blue", re.I)),
    ("Midnight Green", re.compile(r"midnight\s*green", re.I)),
    ("Graphite", re.compile(r"\bgraphite\b|графит", re.I)),
    ("Midnight", re.compile(r"\bmidnight\b|полночь", re.I)),
    ("Starlight", re.compile(r"\bstarlight\b|звёздный|звездный", re.I)),
    ("Product Red", re.compile(r"product\s*red|\(product\)\s*red", re.I)),
    ("Deep Purple", re.compile(r"deep\s*purple|тёмно\s*-?\s*фиолет", re.I)),
    ("Alpine Green", re.compile(r"alpine\s*green", re.I)),
    ("Gold", re.compile(r"\bgold\b|золотой|золото", re.I)),
    ("Silver", re.compile(r"\bsilver\b|серебрист|серебро", re.I)),
    ("Black", re.compile(r"\bblack\b|чёрный|черный", re.I)),
    ("White", re.compile(r"\bwhite\b|белый", re.I)),
    ("Blue", re.compile(r"\bblue\b|синий|голубой", re.I)),
    ("Green", re.compile(r"\bgreen\b|зелёный|зеленый", re.I)),
    ("Purple", re.compile(r"\bpurple\b|фиолетов", re.I)),
    ("Pink", re.compile(r"\bpink\b|розовый", re.I)),
    ("Yellow", re.compile(r"\byellow\b|жёлтый|желтый", re.I)),
    ("Orange", re.compile(r"\borange\b|оранжевый", re.I)),
    ("Red", re.compile(r"\bred\b|красный", re.I)),
    ("Gray", re.compile(r"\bgr[ae]y\b|серый", re.I)),
    ("Titanium", re.compile(r"\btitanium\b|титан", re.I)),
]

_SERIAL_PARENS = re.compile(r"\(\s*[A-Z0-9]{8,}\s*\)", re.IGNORECASE)
_BOOKING_MARK = re.compile(r"\s*\(Бронь от [^)]+\)\s*", re.IGNORECASE)
_EXCHANGE_MARK = re.compile(r"[\(（]\s*[OoОо0]\s*[\)）]")


def _norm_memory(num: str, unit_raw: str) -> str:
    n = int(num)
    unit = unit_raw.upper().replace("ГБ", "GB").replace("GБ", "GB")
    unit = unit.replace("ТБ", "TB").replace("TБ", "TB")
    if "T" in unit:
        return f"{n}TB"
    return f"{n}GB"


def parse_sku_attrs(text: str | None) -> dict[str, str]:
    """
    Извлекает memory / color / sim из строки товара.

    Returns:
        {"memory": "256GB"|"—", "color": "…"|"—", "sim": "…"|"—"}
    """
    raw = text or ""
    cleaned = _BOOKING_MARK.sub(" ", raw)
    cleaned = _SERIAL_PARENS.sub(" ", cleaned)
    cleaned = _EXCHANGE_MARK.sub(" ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    memory = "—"
    m = _MEMORY_RE.search(cleaned)
    if m:
        # group whole match to detect TB vs GB
        full = m.group(0)
        num = m.group(1)
        unit = full[len(num) :].strip()
        memory = _norm_memory(num, unit)

    sim = "—"
    for label, pat in _SIM_PATTERNS:
        if pat.search(cleaned):
            sim = label
            break

    color = "—"
    for label, pat in _COLOR_PHRASES:
        if pat.search(cleaned):
            color = label
            break

    return {"memory": memory, "color": color, "sim": sim}


def build_sku_matrix(items: list[Any]) -> dict[str, Any]:
    """
    Группирует товары по (memory, color, sim).

    items — объекты/dict с полями text, is_booked (и опционально id, serial).
    """
    groups: dict[tuple[str, str, str], dict[str, Any]] = {}

    for it in items:
        if isinstance(it, dict):
            text = it.get("text") or ""
            is_booked = bool(it.get("is_booked"))
            item_id = it.get("id")
            serial = it.get("serial")
        else:
            text = getattr(it, "text", None) or ""
            is_booked = bool(getattr(it, "is_booked", False))
            item_id = getattr(it, "id", None)
            serial = getattr(it, "serial", None)

        attrs = parse_sku_attrs(text)
        key = (attrs["memory"], attrs["color"], attrs["sim"])
        if key not in groups:
            groups[key] = {
                "memory": attrs["memory"],
                "color": attrs["color"],
                "sim": attrs["sim"],
                "free": 0,
                "booked": 0,
                "total": 0,
                "samples": [],
            }
        g = groups[key]
        g["total"] += 1
        if is_booked:
            g["booked"] += 1
        else:
            g["free"] += 1
        if len(g["samples"]) < 3:
            g["samples"].append(
                {"id": item_id, "serial": serial, "text": text[:80]}
            )

    rows = sorted(
        groups.values(),
        key=lambda r: (
            r["memory"] == "—",
            r["memory"],
            r["color"] == "—",
            r["color"].lower(),
            r["sim"],
        ),
    )

    memories = sorted({r["memory"] for r in rows}, key=lambda x: (x == "—", x))
    colors = sorted({r["color"] for r in rows}, key=lambda x: (x == "—", x.lower()))
    sims = sorted({r["sim"] for r in rows}, key=lambda x: (x == "—", x))

    return {
        "rows": rows,
        "memories": memories,
        "colors": colors,
        "sims": sims,
        "total_items": sum(r["total"] for r in rows),
        "total_free": sum(r["free"] for r in rows),
        "total_booked": sum(r["booked"] for r in rows),
        "variant_count": len(rows),
    }
