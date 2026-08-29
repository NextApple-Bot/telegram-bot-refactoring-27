# bot/utils/sort.py
import re


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
    """
    s = normalize_name(name or "").lower().rstrip(":").strip()
    s = re.sub(r"[•·|/]+", " ", s)
    s = re.sub(r"[()\[\]]", " ", s)

    # Series → S (главное правило)
    s = re.sub(r"\bseries\b", "s", s, flags=re.IGNORECASE)
    # S 11 / S11 / s 11 → s11
    s = re.sub(r"\bs\s*(\d+)\b", r"s\1", s)
    # SE 3 → se3
    s = re.sub(r"\bse\s*(\d+)\b", r"se\1", s)

    s = s.replace("apple watch", "watch")
    s = s.replace("samsung galaxy", "galaxy")
    s = s.replace("macbook air", "macbookair")
    s = s.replace("macbook pro", "macbookpro")
    s = s.replace("macbook neo", "macbookneo")
    s = s.replace("macbook 13 neo", "macbookneo")
    s = s.replace("airpods pro", "airpodspro")
    s = s.replace("airpods max", "airpodsmax")
    s = re.sub(r"\s+", "", s)
    return s


def is_marker_line(text: str) -> bool:
    """Служебные строки, не товары."""
    s = (text or "").strip()
    if not s or s == "-":
        return True
    if re.match(r"^-+$", s):
        return True
    if re.match(
        r"^-?\s*(\d+\s*(GB|TB|mm)|eSIM|SIM\+eSIM|SIM)\s*-?$",
        s,
        re.IGNORECASE,
    ):
        return True
    if re.match(r"^(eSIM|SIM\+eSIM|SIM)\s*-\s*$", s, re.IGNORECASE):
        return True
    return False


def extract_memory(text):
    if not text or is_marker_line(text):
        return None
    m = re.search(
        r"\d+\s*/\s*(\d+(?:[.,]\d+)?)\s*(gb|гб|tb|тб)\b",
        text,
        re.IGNORECASE,
    )
    if m:
        num = m.group(1).replace(",", ".")
        unit = m.group(2).lower()
    else:
        m = re.search(
            r"(\d+(?:[.,]\d+)?)\s*(gb|гб|tb|тб)\b",
            text,
            re.IGNORECASE,
        )
        if not m:
            return None
        num = m.group(1).replace(",", ".")
        unit = m.group(2).lower()

    try:
        f = float(num)
        num_fmt = str(int(f)) if f == int(f) else num
    except ValueError:
        num_fmt = num

    if unit in ("гб", "gb"):
        unit = "GB"
    else:
        unit = "TB"
    return f"{num_fmt}{unit}"


def extract_memory_gb(text):
    label = extract_memory(text)
    if not label:
        return None
    m = re.match(r"(\d+(?:[.,]\d+)?)(GB|TB)", label, re.IGNORECASE)
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    if m.group(2).upper() == "TB":
        return int(num * 1024)
    return int(num)


def extract_watch_size(text):
    if not text or is_marker_line(text):
        return None
    match = re.search(r"(\d{2})\s*mm\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def detect_sim_type(text):
    if is_marker_line(text):
        return "other"
    lower = (text or "").lower()
    if re.search(r"\(sim\s*\+\s*esim\)|\bsim\s*\+\s*esim\b", lower):
        return "SIM+eSIM"
    if re.search(r"\(esim\)|\besim\b", lower):
        return "eSIM"
    if re.search(r"\(sim\)|\bsim\b", lower) and "esim" not in lower:
        return "SIM"
    return "other"


def get_full_model_name(item):
    without_brackets = re.sub(r"\([^)]*\)", "", item)
    return normalize_name(without_brackets)


def extract_base_name(item):
    without_brackets = re.sub(r"\([^)]*\)", "", item)
    if "," in without_brackets:
        model_part = without_brackets.split(",", 1)[0].strip()
    else:
        model_part = without_brackets.strip()
    memory = extract_memory(without_brackets)
    base = f"{model_part} {memory}" if memory else model_part
    base = normalize_name(base)
    base = normalize_model(base)
    # Series → S и в базовом имени
    base = re.sub(r"\bSeries\b", "S", base, flags=re.IGNORECASE)
    base = re.sub(r"\bS\s+(\d+)\b", r"S\1", base, flags=re.IGNORECASE)
    return base


def match_existing_category(item_text: str, categories: list) -> str | None:
    """
    Подбирает ТОЛЬКО существующую категорию. Новые не создаёт.
    Series всегда приравнивается к S.
    """
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
            if i + 1 < n and ":" in lines[i + 1]:
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

        if stripped.startswith("-") and stripped.endswith("-") and ":" in stripped:
            flush()
            header_text = stripped.strip("- ").strip()
            if header_text.endswith(":"):
                header_text = header_text[:-1].strip()
            current_header = normalize_name(header_text)
            i += 1
            continue

        if (
            re.match(r"^\s*-+\s*$", stripped)
            and i + 1 < n
            and ":" in lines[i + 1]
            and i + 2 < n
            and re.match(r"^\s*-+\s*$", lines[i + 2])
        ):
            flush()
            header_line = lines[i + 1].strip()
            header_text = header_line.strip("- ").strip()
            if header_text.endswith(":"):
                header_text = header_text[:-1].strip()
            current_header = normalize_name(header_text)
            i += 3
            continue

        if is_marker_line(stripped):
            i += 1
            continue

        if stripped.endswith(":") and len(stripped) < 80:
            if re.search(r"\([A-Z0-9]{6,}\)", stripped):
                pass
            else:
                flush()
                header_text = stripped.rstrip(":").strip()
                current_header = normalize_name(header_text)
                i += 1
                continue

        if current_header is None:
            current_header = "Общее"

        item_text = stripped.lstrip("- ").strip()
        if item_text and not is_marker_line(item_text):
            current_items.append(item_text)
        i += 1

    flush()
    return categories


def sort_assortment_to_categories(input_text):
    return parse_categories(input_text.splitlines())


def _filter_real_items(item_strings):
    return [s for s in item_strings if s and not is_marker_line(s)]


def _export_preserve_order_with_markers(item_strings, header):
    items = _filter_real_items(item_strings)
    if not items:
        return []

    header_lower = (header or "").lower()
    has_watch = any(extract_watch_size(s) is not None for s in items)
    has_memory = any(extract_memory(s) is not None for s in items)
    is_watch = "watch" in header_lower or (
        has_watch and not has_memory and sum(1 for s in items if extract_watch_size(s)) >= max(1, len(items) // 2)
    )

    output = []
    prev_vol = object()
    prev_sim = object()
    prev_size = object()

    for item in items:
        if is_watch:
            size = extract_watch_size(item)
            if size != prev_size:
                if output and output[-1].strip() != "-":
                    output.append("-")
                if size is not None:
                    output.append(f"-{size}mm-")
                output.append("-")
                prev_size = size
            output.append(item)
        elif has_memory:
            vol = extract_memory(item)
            sim = detect_sim_type(item)
            vol_changed = vol != prev_vol
            sim_changed = sim != prev_sim
            if vol_changed or (sim_changed and sim != "other"):
                if output and output[-1].strip() != "-":
                    output.append("-")
                if vol_changed and vol is not None:
                    output.append(f"-{vol}-")
                    prev_sim = object()
                    sim_changed = True
                if sim_changed and sim != "other":
                    output.append(f"-{sim}-")
                output.append("-")
                prev_vol = vol
                prev_sim = sim
            output.append(item)
        else:
            output.append(item)

    return output


def _sort_by_memory_and_sim(item_strings):
    item_strings = _filter_real_items(item_strings)
    groups = {}
    for item_str in item_strings:
        sim = detect_sim_type(item_str)
        vol_gb = extract_memory_gb(item_str)
        vol_str = extract_memory(item_str)
        key = (vol_gb, vol_str)
        if key not in groups:
            groups[key] = {"eSIM": [], "SIM+eSIM": [], "SIM": [], "other": []}
        groups[key][sim].append(item_str)

    sorted_keys = sorted(
        groups.keys(),
        key=lambda k: (k[0] is None, k[0] if k[0] is not None else float("inf")),
    )

    output = []
    for vol_gb, vol_str in sorted_keys:
        bucket = groups[(vol_gb, vol_str)]
        total_in_vol = sum(len(bucket[s]) for s in bucket)
        if total_in_vol == 0:
            continue

        if output:
            output.append("-")

        if vol_str is not None:
            output.append(f"-{vol_str}-")

        first_sim_in_vol = True
        for sim_type in ["eSIM", "SIM+eSIM", "SIM", "other"]:
            items_list = bucket[sim_type]
            if not items_list:
                continue

            if not first_sim_in_vol:
                output.append("-")

            if sim_type != "other":
                output.append(f"-{sim_type}-")

            output.append("-")
            output.extend(items_list)
            first_sim_in_vol = False

    return output


def _sort_by_watch_size(item_strings):
    item_strings = _filter_real_items(item_strings)
    size_groups = {}
    for item_str in item_strings:
        size = extract_watch_size(item_str)
        size_groups.setdefault(size, []).append(item_str)

    sorted_sizes = sorted(
        size_groups.keys(),
        key=lambda s: (s is None, s if s is not None else float("inf")),
    )
    output = []
    for size in sorted_sizes:
        items_list = size_groups[size]
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
    return _filter_real_items(item_strings)


_PHONE_BRANDS = (
    "iphone", "ipad", "macbook", "mac mini", "imac", "ipod",
    "samsung", "galaxy", "huawei", "xiaomi", "redmi", "poco",
    "pixel", "oneplus", "honor", "realme", "oppo", "vivo",
    "nothing", "motorola", "nokia", "sony", "xperia", "asus",
    "rog phone", "zte", "tecno", "infinix",
)


def sort_items_in_category(items, header, preserve_order: bool = True):
    if items and isinstance(items[0], dict):
        item_strings = [item.get("text", "") for item in items if item.get("text")]
    else:
        item_strings = [str(x) for x in items if str(x).strip()]

    item_strings = _filter_real_items(item_strings)
    if not item_strings:
        return []

    header_lower = (header or "").lower()
    has_watch_size = any(extract_watch_size(s) is not None for s in item_strings)
    has_memory = any(extract_memory(s) is not None for s in item_strings)
    watch_count = sum(1 for s in item_strings if extract_watch_size(s) is not None)

    is_watch = (
        "watch" in header_lower
        or (
            has_watch_size
            and watch_count >= max(1, (len(item_strings) + 1) // 2)
            and not has_memory
        )
    )

    is_memory_device = has_memory or any(b in header_lower for b in _PHONE_BRANDS)

    # После «прибытия» новые позиции идут в конец (по id).
    # Если просто «сохранять порядок», появляются повторные блоки -256GB- / -eSIM-.
    # Для телефонов / часов / памяти всегда пересобираем группы.
    if is_watch:
        return _sort_by_watch_size(item_strings)
    if is_memory_device:
        return _sort_by_memory_and_sim(item_strings)

    if preserve_order:
        return _export_preserve_order_with_markers(item_strings, header)
    return _sort_plain(item_strings)


def build_output_text(categories, preserve_order: bool = True):
    output_lines = []
    for cat in categories:
        header = cat.get("header") or cat.get("name")
        if not header:
            continue
        if str(header).strip() == "__SYSTEM__":
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
        sorted_output = (
            sort_items_in_category(items, header, preserve_order=preserve_order)
            if items
            else []
        )
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
