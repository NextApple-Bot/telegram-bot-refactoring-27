# bot/utils/sort.py
import logging
import re

logger = logging.getLogger(__name__)

# Маркер «товар завершён» в скобках (SN / № / количество).
# Без этого строки без длинного SN склеиваются:
#   Яндекс Станция … (4ШТ) Яндекс Станция … (1ШТ)
_SERIAL_IN_PARENS = re.compile(
    r"[\(\[]("
    r"[A-Za-z0-9\-]{6,}"          # обычный SN
    r"|S?№\s*\d+"                # (№5) / (S№10)
    r"|№\s*\d+"
    r"|\d+\s*ШТ"                 # (4ШТ) / (4 ШТ)
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
# Любые скобки в конце строки — почти всегда законченный товар
# (не трогаем «Size: L» и прочие продолжения без скобок)
_TRAILING_PARENS = re.compile(r"[\(\[][^\)\]]{1,40}[\)\]]\s*$")

# Маркеры памяти / SIM / размера, которые НЕ должны становиться категориями
_MEMORY_OR_SIM_MARKER_RE = re.compile(
    r"^\s*-?\s*(\d+\s*(GB|TB|mm)|eSIM|SIM\+eSIM|SIM)\s*-?\s*$",
    re.IGNORECASE,
)


def normalize_name(name):
    return " ".join(str(name).split())


def normalize_model(name):
    return re.sub(r"S\s+(\d+)", r"S\1", name, flags=re.IGNORECASE)


def normalize_category_key(name: str) -> str:
    """
    Ключ для сопоставления категорий.
    Series всегда = S:
      Apple Watch Series 11  ↔  Apple Watch S11
      Series 10              ↔  S10
    RayBan / Ray-Ban / Ray Ban → rayban (дефисы и пробелы убираем)
    """
    s = normalize_name(name or "").lower().rstrip(":").strip()
    s = re.sub(r"[•·|/]+", " ", s)
    s = re.sub(r"[()\[\]]", " ", s)

    s = re.sub(r"\bseries\b", "s", s, flags=re.IGNORECASE)
    s = re.sub(r"\bs\s*(\d+)\b", r"s\1", s)
    s = re.sub(r"\bse\s*(\d+)\b", r"se\1", s)

    s = s.replace("apple watch", "watch")
    s = s.replace("samsung galaxy", "galaxy")
    s = s.replace("macbook air", "macbookair")
    s = s.replace("macbook pro", "macbookpro")
    s = s.replace("macbook neo", "macbookneo")
    s = s.replace("macbook 13 neo", "macbookneo")
    s = s.replace("airpods pro", "airpodspro")
    s = s.replace("airpods max", "airpodsmax")
    # Ray-Ban Meta ↔ RayBan, S-серии без дефисов
    s = s.replace("-", "")
    s = re.sub(r"\s+", "", s)
    return s


def is_marker_line(text: str) -> bool:
    """Служебные строки, не товары."""
    s = (text or "").strip()
    if not s or s == "-":
        return True
    if re.match(r"^-+$", s):
        return True
    if _MEMORY_OR_SIM_MARKER_RE.match(s):
        return True
    if re.match(r"^(eSIM|SIM\+eSIM|SIM)\s*-\s*$", s, re.IGNORECASE):
        return True
    return False
