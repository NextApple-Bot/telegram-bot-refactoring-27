# bot/utils/sort_parse.py
import logging
import re

from bot.utils.sort_normalize import (
    normalize_name,
    normalize_model,
    normalize_item_text,
    _SERIAL_IN_PARENS,
    _ONLY_SERIAL_LINE,
    _TRAILING_PARENS,
    _MEMORY_OR_SIM_MARKER_RE,
)

logger = logging.getLogger(__name__)


def normalize_category_key(name: str) -> str:
    """RayBan / Ray-Ban / Ray Ban → rayban; Series → S."""
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
    s = s.replace("-", "")
    s = re.sub(r"\s+", "", s)
    return s


def is_marker_line(text: str) -> bool:
    s = (text or "").strip()
    if not s or s == "-":
        return True
    if re.match(r"^-+$", s):
        return True
    if _MEMORY_OR_SIM_MARKER_RE.match(s):
        return True
    if re.match(r"^(eSIM|SIM\+eSIM|SIM|Dual SIM)\s*-\s*$", s, re.IGNORECASE):
        return True
    return False


def _has_product_serial(text: str) -> bool:
    s = text or ""
    if _SERIAL_IN_PARENS.search(s):
        return True
    if _TRAILING_PARENS.search(s.strip()):
        return True
    return False


def _looks_like_category_header(text: str) -> bool:
    s = (text or "").strip()
    if not s or len(s) > 60:
        return False
    if not s.endswith(":"):
        return False
    if _has_product_serial(s):
        return False
    body = s[:-1].strip()
    if not body or len(body) < 2:
        return False
    if _MEMORY_OR_SIM_MARKER_RE.match(body) or _MEMORY_OR_SIM_MARKER_RE.match(f"-{body}-"):
        return False
    if re.match(r"^\d+\s*(GB|TB|mm)$", body, re.IGNORECASE):
        return False
    if body.upper() in ("ESIM", "SIM", "SIM+ESIM", "SIM + ESIM", "DUAL SIM"):
        return False
    if "," in body or " / " in body or re.search(r"\bSize\s*:", body, re.I):
        return False
    if re.search(r"\b(Gen\s*\d+|mm)\b", body, re.I):
        return False
    return True


def extract_memory(text):
    if not text or is_marker_line(text):
        return None
    m = re.search(r"\d+\s*/\s*(\d+(?:[.,]\d+)?)\s*(gb|гб|tb|тб)\b", text, re.IGNORECASE)
    if m:
        num = m.group(1).replace(",", ".")
        unit = m.group(2).lower()
    else:
        m = re.search(r"(\d+(?:[.,]\d+)?)\s*(gb|гб|tb|тб)\b", text, re.IGNORECASE)
        if not m:
            return None
        num = m.group(1).replace(",", ".")
        unit = m.group(2).lower()
    try:
        f = float(num)
        num_fmt = str(int(f)) if f == int(f) else num
    except ValueError:
        num_fmt = num
    unit = "GB" if unit in ("гб", "gb") else "TB"
    return f"{num_fmt}{unit}"


def extract_memory_gb(text):
    label = extract_memory(text)
    if not label:
        return None
    m = re.match(r"(\d+(?:[.,]\d+)?)(GB|TB)", label, re.IGNORECASE)
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    return int(num * 1024) if m.group(2).upper() == "TB" else int(num)


def extract_watch_size(text):
    if not text or is_marker_line(text):
        return None
    match = re.search(r"(\d{2})\s*mm\b", text, re.IGNORECASE)
    return int(match.group(1)) if match else None


def detect_sim_type(text):
    if is_marker_line(text):
        return "other"
    lower = (text or "").lower()
    if re.search(r"sim\s*\+\s*esim|sim\s*\+\s*e\s*sim", lower):
        return "SIM+eSIM"
    if re.search(r"\bdual\s*sim\b|\b2\s*sim\b", lower):
        return "Dual SIM"
    if re.search(r"\besim\b", lower):
        return "eSIM"
    if re.search(r"\bsim\b", lower):
        return "SIM"
    return "other"


def get_full_model_name(item):
    return normalize_name(re.sub(r"\([^)]*\)", "", item))


def extract_base_name(item):
    without_brackets = re.sub(r"\([^)]*\)", "", item)
    model_part = without_brackets.split(",", 1)[0].strip() if "," in without_brackets else without_brackets.strip()
    memory = extract_memory(without_brackets)
    base = f"{model_part} {memory}" if memory else model_part
    base = normalize_name(base)
    base = normalize_model(base)
    base = re.sub(r"\bSeries\b", "S", base, flags=re.IGNORECASE)
    base = re.sub(r"\bS\s+(\d+)\b", r"S\1", base, flags=re.IGNORECASE)
    return base


def match_existing_category(item_text: str, categories: list) -> str | None:
    if not categories:
        return None
    stripped = (item_text or "").strip()
    low = stripped.lower()
    if low.startswith("б/у -") or low.startswith("б/у "):
        for cat in categories:
            h = normalize_name(cat.get("header") or "").lower().rstrip(":")
            if h in ("б/у", "bu"):
                return cat.get("header") or cat.get("name")
    if low.startswith("ns -") or low.startswith("ns "):
        for cat in categories:
            h = normalize_name(cat.get("header") or "").lower().rstrip(":")
            if h == "ns":
                return cat.get("header") or cat.get("name")

    item_key = normalize_category_key(extract_base_name(stripped))
    item_full_key = normalize_category_key(stripped)
    best = None
    best_score = 0
    for cat in categories:
        header = cat.get("header") or cat.get("name") or ""
        if not header or str(header).strip() == "__SYSTEM__":
            continue
        cat_key = normalize_category_key(header)
        if not cat_key:
            continue
        score = 0
        if cat_key == item_key or cat_key == item_full_key:
            score = 1000 + len(cat_key)
        elif item_key.startswith(cat_key) or cat_key in item_key:
            score = 500 + len(cat_key)
        elif item_full_key.startswith(cat_key) or cat_key in item_full_key:
            score = 400 + len(cat_key)
        else:
            if len(cat_key) >= 4 and cat_key in item_full_key:
                score = 200 + len(cat_key)
            elif len(item_key) >= 4 and item_key in cat_key:
                score = 150 + len(item_key)
        if score > best_score:
            best_score = score
            best = header
    if best_score >= 150:
        return best
    for cat in categories:
        h = normalize_name(cat.get("header") or "").lower().rstrip(":")
        if h in ("общее", "общий", "other", "misc"):
            return cat.get("header") or cat.get("name")
    return None


def _merge_multiline_items(lines: list[str]) -> list[str]:
    out: list[str] = []
    buf: list[str] = []

    def flush_buf():
        nonlocal buf
        if not buf:
            return
        out.append(" ".join(buf))
        buf = []

    for raw in lines:
        line = raw.rstrip("\n")
        stripped = line.strip()
        if stripped == "" or is_marker_line(stripped) or re.match(r"^-{3,}$", stripped):
            flush_buf()
            out.append(line)
            continue
        if _looks_like_category_header(stripped):
            flush_buf()
            out.append(line)
            continue
        only_serial = bool(_ONLY_SERIAL_LINE.match(stripped))
        has_serial = _has_product_serial(stripped)
        if buf:
            buf.append(stripped)
            if has_serial or only_serial:
                flush_buf()
            continue
        if has_serial or only_serial:
            out.append(stripped)
            continue
        buf = [stripped]
    flush_buf()
    return out


def parse_categories(lines):
    categories = []
    current_header = None
    current_items = []
    i = 0
    n = len(lines)

    def flush():
        nonlocal current_header, current_items
        if current_header is not None:
            categories.append({"header": current_header, "items": list(current_items)})
            current_items = []

    while i < n:
        line = lines[i].rstrip("\n")
        stripped = line.strip()
        if stripped == "":
            i += 1
            continue
        if re.match(r"^-{3,}$", stripped):
            if i + 1 < n and _looks_like_category_header(lines[i + 1].strip()):
                flush()
                header_line = lines[i + 1].strip()
                header_text = header_line.rstrip(":").strip()
                current_header = normalize_name(header_text)
                i += 2
                if i < n and re.match(r"^-{3,}$", lines[i].strip()):
                    i += 1
                continue
            i += 1
            continue
        if is_marker_line(stripped):
            i += 1
            continue
        if _looks_like_category_header(stripped):
            flush()
            header_text = stripped.rstrip(":").strip()
            current_header = normalize_name(header_text)
            i += 1
            continue
        if current_header is None:
            current_header = "Общее"
        item_text = stripped.lstrip("- ").strip()
        if item_text and not is_marker_line(item_text):
            current_items.append(normalize_item_text(item_text))
        i += 1
    flush()
    return categories


def sort_assortment_to_categories(input_text):
    return parse_categories(_merge_multiline_items(input_text.splitlines()))


def _filter_real_items(item_strings):
    return [s for s in item_strings if s and not is_marker_line(s)]


# «№5», «S№10», «№ 12» — сортировка от меньшего к большему
_NUM_MARK_RE = re.compile(r"[Ss]?№\s*(\d+)")


def _extract_num_mark(text: str) -> int | None:
    m = _NUM_MARK_RE.search(text or "")
    return int(m.group(1)) if m else None


def _item_sort_key(text: str):
    """Сначала по номеру №N (если есть), иначе алфавит."""
    n = _extract_num_mark(text)
    return (n is None, n if n is not None else 0, (text or "").lower())


def _sort_by_memory_and_sim(item_strings):
    item_strings = _filter_real_items(item_strings)
    groups: dict = {}
    for item_str in item_strings:
        sim = detect_sim_type(item_str)
        vol_gb = extract_memory_gb(item_str)
        vol_str = extract_memory(item_str)
        key = (vol_gb if vol_gb is not None else -1, vol_str or "")
        if key not in groups:
            groups[key] = {"eSIM": [], "SIM+eSIM": [], "Dual SIM": [], "SIM": [], "other": []}
        groups[key][sim].append(item_str)
    sorted_keys = sorted(groups.keys(), key=lambda k: (k[0] < 0, k[0] if k[0] >= 0 else 10**9))
    output = []
    for key in sorted_keys:
        vol_gb, vol_str = key
        bucket = groups[key]
        if sum(len(bucket[s]) for s in bucket) == 0:
            continue
        if output:
            output.append("-")
        if vol_str:
            output.append(f"-{vol_str}-")
        first_sim = True
        for sim_type in ["eSIM", "SIM+eSIM", "Dual SIM", "SIM", "other"]:
            items_list = bucket[sim_type]
            if not items_list:
                continue
            items_list = sorted(items_list, key=_item_sort_key)
            if not first_sim:
                output.append("-")
            if sim_type != "other":
                output.append(f"-{sim_type}-")
            output.append("-")
            output.extend(items_list)
            first_sim = False
    return output


def _sort_by_watch_size(item_strings):
    item_strings = _filter_real_items(item_strings)
    size_groups: dict = {}
    for item_str in item_strings:
        size = extract_watch_size(item_str)
        size_groups.setdefault(size, []).append(item_str)
    sorted_sizes = sorted(size_groups.keys(), key=lambda s: (s is None, s if s is not None else float("inf")))
    output = []
    for size in sorted_sizes:
        items_list = sorted(size_groups[size], key=_item_sort_key)
        if not items_list:
            continue
        if output:
            output.append("-")
        if size is not None:
            output.append(f"-{size}mm-")
        output.append("-")
        output.extend(items_list)
    return output


def _sort_plain(item_strings):
    items = _filter_real_items(item_strings)
    return sorted(items, key=_item_sort_key)


_PHONE_BRANDS = (
    "iphone", "ipad", "macbook", "mac mini", "imac", "ipod",
    "samsung", "galaxy", "huawei", "xiaomi", "redmi", "poco",
    "pixel", "oneplus", "honor", "realme", "oppo", "vivo",
    "nothing", "motorola", "nokia", "sony", "xperia", "asus",
    "rog phone", "zte", "tecno", "infinix", "playstation", "dualsense",
)


def sort_items_in_category(items, header, preserve_order: bool = False):
    if items and isinstance(items[0], dict):
        item_strings = [item.get("text", "") for item in items if item.get("text")]
    else:
        item_strings = [str(x) for x in items if str(x).strip()]
    item_strings = [normalize_item_text(s) for s in item_strings]
    item_strings = _filter_real_items(item_strings)
    if not item_strings:
        return []
    header_lower = (header or "").lower()
    has_watch_size = any(extract_watch_size(s) is not None for s in item_strings)
    has_memory = any(extract_memory(s) is not None for s in item_strings)
    watch_count = sum(1 for s in item_strings if extract_watch_size(s) is not None)
    is_watch = (
        "watch" in header_lower
        or (has_watch_size and watch_count >= max(1, (len(item_strings) + 1) // 2) and not has_memory)
    )
    is_memory_device = has_memory or any(b in header_lower for b in _PHONE_BRANDS)
    if is_watch:
        return _sort_by_watch_size(item_strings)
    if is_memory_device:
        return _sort_by_memory_and_sim(item_strings)
    return _sort_plain(item_strings)


def build_output_text(categories, preserve_order: bool = False):
    output_lines = []
    for cat in categories:
        header = cat.get("header") or cat.get("name")
        if not header or str(header).strip() == "__SYSTEM__":
            continue
        display_header = normalize_name(header)
        if not display_header.endswith(":"):
            display_header += ":"
        dash_len = max(len(display_header) + 2, 12)
        output_lines.append("-" * dash_len)
        output_lines.append(display_header)
        output_lines.append("-" * dash_len)
        output_lines.append("-")
        items = cat.get("items", []) or []
        sorted_output = sort_items_in_category(items, header, preserve_order=False) if items else []
        output_lines.extend(sorted_output)
        if sorted_output and sorted_output[-1].strip() != "-":
            output_lines.append("-")
        output_lines.append("")
    while output_lines and output_lines[-1] == "":
        output_lines.pop()
    return "\n".join(output_lines)


def find_category_for_item(item, categories):
    matched = match_existing_category(item, categories)
    if matched is None:
        return None
    for idx, cat in enumerate(categories):
        if (cat.get("header") or cat.get("name")) == matched:
            return idx
    return None


def add_item_to_categories(item, categories):
    matched = match_existing_category(item, categories)
    if matched is None:
        return categories, None
    for idx, cat in enumerate(categories):
        if (cat.get("header") or cat.get("name")) == matched:
            categories[idx]["items"].append(item)
            return categories, idx
    return categories, None
