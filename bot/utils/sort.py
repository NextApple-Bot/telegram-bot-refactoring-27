# bot/utils/sort.py
import logging
import re

logger = logging.getLogger(__name__)

_SERIAL_IN_PARENS = re.compile(
    r"[\(\[]("
    r"[A-Za-z0-9\-]{6,}"
    r"|S?№\s*\d+"
    r"|№\s*\d+"
    r"|\d+\s*ШТ"
    r"|\d+\s*шт"
    r")[\)\]]",
    re.IGNORECASE,
)
_ONLY_SERIAL_LINE = re.compile(
    r"^[\(\[]("
    r"[A-Za-z0-9\-]{6,}"
    r"|S?№\s*\d+"
    r"|\d+\s*ШТ"
    r"|\d+\s*шт"
    r")[\)\]]$",
    re.IGNORECASE,
)
_TRAILING_PARENS = re.compile(r"[\(\[][^\)\]]{1,40}[\)\]]\s*$")
_MEMORY_OR_SIM_MARKER_RE = re.compile(
    r"^\s*-?\s*(\d+\s*(GB|TB|mm)|eSIM|SIM\+eSIM|SIM|Dual SIM)\s*-?\s*$",
    re.IGNORECASE,
)


def normalize_name(name):
    return " ".join(str(name).split())


def normalize_model(name):
    return re.sub(r"S\s+(\d+)", r"S\1", name, flags=re.IGNORECASE)


def normalize_item_text(text: str) -> str:
    """
    Единый «красивый» вид названия товара.
    Apple Watch / iPhone / iPad / MacBook / AirPods / Samsung / Marshall + общее.
    Три типа SIM: eSIM | SIM+eSIM | Dual SIM.
    Серийник в скобках сохраняется.
    """
    if not text:
        return text
    s = str(text).strip()
    s = re.sub(r"\s+", " ", s)

    # --- общее: память, Wi-Fi ---
    s = re.sub(r"\bWi[\s\-]?Fi\b", "Wi-Fi", s, flags=re.IGNORECASE)

    def _mem_pair(m):
        unit = m.group(3).upper().replace("ГБ", "GB").replace("ТБ", "TB")
        return f"{m.group(1)}/{m.group(2).replace(',', '.')}{unit}"

    def _mem_one(m):
        unit = m.group(2).upper().replace("ГБ", "GB").replace("ТБ", "TB")
        return f"{m.group(1).replace(',', '.')}{unit}"

    s = re.sub(
        r"(\d+)\s*/\s*(\d+(?:[.,]\d+)?)\s*(GB|ГБ|TB|ТБ)\b",
        _mem_pair,
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(\d+(?:[.,]\d+)?)\s*(GB|ГБ|TB|ТБ)\b",
        _mem_one,
        s,
        flags=re.IGNORECASE,
    )

    # --- SIM: три отдельных типа (порядок важен) ---
    s = re.sub(
        r"\(?\s*2\s*SIM\s*\)?",
        "(Dual SIM)",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\bDual\s*SIM\b",
        "Dual SIM",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\(\s*Dual SIM\s*\)", "(Dual SIM)", s)
    s = re.sub(r"\(Dual SIM\)(?:\s*\(Dual SIM\))+", "(Dual SIM)", s)
    s = re.sub(
        r"\bSIM\s*\+\s*e?\s*SIM\b",
        "SIM+eSIM",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\be\s*SIM\b", "eSIM", s, flags=re.IGNORECASE)

    # --- Apple Watch ---
    s = re.sub(
        r"\bApple Watch\s+Series\s+(\d+)\b",
        r"Apple Watch S\1",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\bApple Watch\s+S\s*(\d+)\b",
        r"Apple Watch S\1",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\bApple Watch\s+SE\s*(\d+)\b",
        r"Apple Watch SE \1",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\bApple Watch\s+Ultra\s*(\d+)\b",
        r"Apple Watch Ultra \1",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\bApple Watch\s+Ultra\b(?!\s*\d)",
        "Apple Watch Ultra",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\bGPS\s*\+\s*Cellular\b", "GPS+Cellular", s, flags=re.IGNORECASE)
    s = re.sub(r"\bGPS\s+Cellular\b", "GPS+Cellular", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(Apple Watch (?:S\d+|SE(?:\s*\d+)?|Ultra(?:\s+\d+)?)),?\s*(\d+\s*mm),?\s+",
        r"\1, \2, ",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\b(\d+)\s*mm\b", r"\1mm", s, flags=re.IGNORECASE)
    s = re.sub(r"\bBlack\s*Ti\b", "Black Titanium", s, flags=re.IGNORECASE)

    # --- iPhone ---
    s = re.sub(r"\bi\s*Phone\b", "iPhone", s, flags=re.IGNORECASE)
    s = re.sub(r"\bIPHONE\b", "iPhone", s)
    s = re.sub(
        r"\biPhone\s+(\d+)\s*Pro\s*Max\b",
        r"iPhone \1 Pro Max",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\biPhone\s+(\d+)\s*Pro\b(?!\s*Max)",
        r"iPhone \1 Pro",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\biPhone\s+(\d+)\s*Plus\b",
        r"iPhone \1 Plus",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\biPhone\s+(\d+)\s*Air\b",
        r"iPhone \1 Air",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\bNatural\s*Ti\b", "Natural Titanium", s, flags=re.IGNORECASE)
    s = re.sub(r"\bWhite\s*Ti\b", "White Titanium", s, flags=re.IGNORECASE)
    s = re.sub(r"\bBlack\s*Ti\b", "Black Titanium", s, flags=re.IGNORECASE)
    s = re.sub(r"\bDesert\s*Ti\b", "Desert Titanium", s, flags=re.IGNORECASE)
    s = re.sub(r"\bBlue\s*Ti\b", "Blue Titanium", s, flags=re.IGNORECASE)
    s = re.sub(r"\bGray\s*Ti\b", "Gray Titanium", s, flags=re.IGNORECASE)
    s = re.sub(r"\bGrey\s*Ti\b", "Gray Titanium", s, flags=re.IGNORECASE)

    _color_map = [
        ("natural titanium", "Natural Titanium"),
        ("white titanium", "White Titanium"),
        ("black titanium", "Black Titanium"),
        ("desert titanium", "Desert Titanium"),
        ("blue titanium", "Blue Titanium"),
        ("gray titanium", "Gray Titanium"),
        ("grey titanium", "Gray Titanium"),
        ("cosmic orange", "Cosmic Orange"),
        ("deep purple", "Deep Purple"),
        ("deep blue", "Deep Blue"),
        ("space black", "Space Black"),
        ("space gray", "Space Gray"),
        ("space grey", "Space Gray"),
        ("starlight", "Starlight"),
        ("midnight", "Midnight"),
        ("product red", "Product Red"),
        ("sierra blue", "Sierra Blue"),
        ("alpine green", "Alpine Green"),
        ("pacific blue", "Pacific Blue"),
        ("rose gold", "Rose Gold"),
        ("jet black", "Jet Black"),
        ("sky blue", "Sky Blue"),
        ("mist blue", "Mist Blue"),
        ("light gold", "Light Gold"),
        ("cloud white", "Cloud White"),
        ("phantom black", "Phantom Black"),
        ("silver shadow", "Silver Shadow"),
        ("silver blue", "Silver Blue"),
        ("cobalt violet", "Cobalt Violet"),
        ("titanium gray", "Titanium Gray"),
        ("titanium grey", "Titanium Gray"),
        ("ultramarine", "Ultramarine"),
        ("lavender", "Lavender"),
        ("silver", "Silver"),
        ("gold", "Gold"),
        ("pink", "Pink"),
        ("purple", "Purple"),
        ("orange", "Orange"),
        ("teal", "Teal"),
        ("yellow", "Yellow"),
        ("green", "Green"),
        ("blue", "Blue"),
        ("black", "Black"),
        ("white", "White"),
        ("red", "Red"),
        ("sage", "Sage"),
        ("navy", "Navy"),
        ("graphite", "Graphite"),
        ("indigo", "Indigo"),
        ("blush", "Blush"),
        ("citrus", "Citrus"),
    ]
    for low, nice in _color_map:
        s = re.sub(rf"\b{re.escape(low)}\b", nice, s, flags=re.IGNORECASE)

    # --- iPad / MacBook ---
    s = re.sub(
        r'\b(MacBook (?:Air|Pro))\s+(13|15|16)(?![\"”])\b',
        r'\1 \2"',
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r'\bMacBook\s+(13|14|16)\s*Pro\b',
        r'MacBook Pro \1"',
        s,
        flags=re.IGNORECASE,
    )
    # MacBook Neo → MacBook Neo, 13", RAM/SSD, Color
    s = re.sub(
        r'\bMacBook\s+13\s*Neo\b',
        "MacBook Neo 13",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r'\bMacBook\s+Neo\s*,?\s*13[\"”]?',
        'MacBook Neo, 13"',
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r'(MacBook Neo,\s*13)"+', r'\1"', s, flags=re.IGNORECASE)
    s = re.sub(
        r'(MacBook Neo,\s*13")\s+(\d+\s*/\s*\d+(?:GB|TB))',
        r'\1, \2',
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r'(MacBook Neo,\s*13",\s*\d+/\d+(?:GB|TB))\s+([A-Za-zА-Яа-яЁё])',
        r'\1, \2',
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r'\b(iPad Pro)\s+(11|13)(?![\"”])\b',
        r'\1 \2"',
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r'\b(iPad Air)\s+(11|13)(?![\"”])\b',
        r'\1 \2"',
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\biPad\s*Air\b", "iPad Air", s, flags=re.IGNORECASE)
    s = re.sub(r"\biPad\s*mini\b", "iPad mini", s, flags=re.IGNORECASE)
    s = re.sub(r"\biPad\s*Pro\b", "iPad Pro", s, flags=re.IGNORECASE)
    s = re.sub(r"\(M(\d+)\)", r"M\1", s)
    s = re.sub(r"\(A(\d+)\)", r"A\1", s)

    # --- AirPods ---
    s = re.sub(r"\bAir\s*Pods\b", "AirPods", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAIRPODS\b", "AirPods", s)
    s = re.sub(r"\bAirPods\s*Pro\s*(\d+)\b", r"AirPods Pro \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAirPods\s*Pro\b(?!\s*\d)", "AirPods Pro", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAirPods\s*Max\b", "AirPods Max", s, flags=re.IGNORECASE)
    s = re.sub(r"\bAirPods\s*(\d+)\b", r"AirPods \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bUSB\s*-?\s*C\b", "USB-C", s, flags=re.IGNORECASE)
    s = re.sub(r"\bType\s*-?\s*C\b", "USB-C", s, flags=re.IGNORECASE)
    s = re.sub(r"\bLight+ing\b", "Lightning", s, flags=re.IGNORECASE)

    # --- Apple Pencil ---
    s = re.sub(r"\bApple\s*Pencil\s*(\d+)\b", r"Apple Pencil \1", s, flags=re.IGNORECASE)
    s = re.sub(r"\bApple\s*Pencil\b", "Apple Pencil", s, flags=re.IGNORECASE)

    # --- Samsung ---
    s = re.sub(r"\bSAMSUNG\b", "Samsung", s)
    s = re.sub(r"\bSamsung\s+Galaxy\b", "Samsung Galaxy", s, flags=re.IGNORECASE)
    s = re.sub(
        r"\b(Samsung\s+)?Galaxy\s+S(\d+)\s*Ultra\b",
        r"Samsung Galaxy S\2 Ultra",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(Samsung\s+)?Galaxy\s+S(\d+)\s*FE\b",
        r"Samsung Galaxy S\2 FE",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(Samsung\s+)?Galaxy\s+S(\d+)\s*\+\b",
        r"Samsung Galaxy S\2+",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(Samsung\s+)?Galaxy\s+S(\d+)\b(?!\s*(?:Ultra|FE|\+))",
        r"Samsung Galaxy S\2",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(Samsung\s+)?Galaxy\s+Z\s*Fold\s*(\d+)\b",
        r"Samsung Galaxy Z Fold \2",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(Samsung\s+)?Galaxy\s+Fold\s*(\d+)\b",
        r"Samsung Galaxy Z Fold \2",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(Samsung\s+)?Galaxy\s+Z\s*Flip\s*(\d+)\b",
        r"Samsung Galaxy Z Flip \2",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"\b(Samsung\s+)?Galaxy\s+A(\d+)\b",
        r"Samsung Galaxy A\2",
        s,
        flags=re.IGNORECASE,
    )
    s = re.sub(
        r"(?<!Galaxy )(?<!Galaxy)(?<![A-Za-z])S(\d+)\s*Ultra\b",
        r"Samsung Galaxy S\1 Ultra",
        s,
        flags=re.IGNORECASE,
    )

    # --- Marshall ---
    s = re.sub(r"\bMarshal+l?\b", "Marshall", s, flags=re.IGNORECASE)

    # --- PlayStation / DualSense ---
    s = re.sub(r"\bDual\s*Sense\b", "DualSense", s, flags=re.IGNORECASE)
    s = re.sub(r"\bPlay\s*Station\b", "PlayStation", s, flags=re.IGNORECASE)
    s = re.sub(r"\bPS\s*5\b", "PS5", s, flags=re.IGNORECASE)

    # --- Ray-Ban ---
    s = re.sub(r"\bRay\s*-?\s*Ban\b", "Ray-Ban", s, flags=re.IGNORECASE)
    s = re.sub(r"\bRayBan\b", "Ray-Ban", s, flags=re.IGNORECASE)

    # --- серийник / пунктуация ---
    s = re.sub(r"[\(\[]\s*([A-Za-z0-9\-]{4,})\s*[\)\]]", r"(\1)", s)
    s = re.sub(r"([A-Za-z0-9])(\([A-Za-z0-9\-]{4,}\))", r"\1 \2", s)
    s = re.sub(r"\s*,\s*", ", ", s)
    s = re.sub(r"\s+", " ", s)

    return s.strip()
