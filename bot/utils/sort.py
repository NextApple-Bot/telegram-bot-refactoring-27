# bot/utils/sort.py
import re


def normalize_name(name):
    return " ".join(name.split())


def normalize_model(name):
    return re.sub(r"S\s+(\d+)", r"S\1", name, flags=re.IGNORECASE)


def extract_memory(text):
    match = re.search(r"(\d+)\s*(gb|гб|tb|тб)", text, re.IGNORECASE)
    if match:
        num = match.group(1)
        unit = match.group(2).lower()
        if unit in ("гб", "gb"):
            unit = "GB"
        elif unit in ("тб", "tb"):
            unit = "TB"
        return f"{num}{unit}"
    return None


def extract_memory_gb(text):
    match = re.search(r"(\d+)\s*(gb|гб|tb|тб)", text, re.IGNORECASE)
    if not match:
        return None
    num = int(match.group(1))
    unit = match.group(2).lower()
    if unit in ("tb", "тб"):
        return num * 1024
    return num


def extract_watch_size(text):
    """Размер часов: 40mm, 41mm, 42mm, 44mm, 45mm, 46mm, 49mm и т.д."""
    match = re.search(r"(\d{2})\s*mm\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def detect_sim_type(text):
    lower = text.lower()
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
    return base


def parse_categories(lines):
    """
    Парсит текст ассортимента в список категорий.
    Пустые категории СОХРАНЯЮТСЯ (items = []).
    """
    categories = []
    current_header = None
    current_items = []
    i = 0
    n = len(lines)

    def flush():
        nonlocal current_header, current_items
        if current_header is not None:
            categories.append({"header": current_header, "items": current_items})
            current_items = []

    while i < n:
        line = lines[i].rstrip("\n")
        stripped = line.strip()

        if stripped == "":
            i += 1
            continue

        # ------------\nHeader:\n------------
        if re.match(r"^-{3,}$", stripped):
            if i + 1 < n and ":" in lines[i + 1]:
                flush()
                header_line = lines[i + 1].strip()
                header_text = header_line.rstrip(":").strip()
                current_header = normalize_name(header_text)
                i += 2
                # пропустить закрывающие -----
                if i < n and re.match(r"^-{3,}$", lines[i].strip()):
                    i += 1
                continue
            i += 1
            continue

        # -Header:-
        if stripped.startswith("-") and stripped.endswith("-") and ":" in stripped:
            flush()
            header_text = stripped.strip("- ").strip()
            if header_text.endswith(":"):
                header_text = header_text[:-1].strip()
            current_header = normalize_name(header_text)
            i += 1
            continue

        # ---\nHeader:\n---
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

        # одиночные ----- или маркеры -
        if re.match(r"^\s*-+\s*$", stripped):
            i += 1
            continue

        if re.match(r"^-\s*[^-]+\s*-$", stripped):
            i += 1
            continue

        # Header: без рамок
        if stripped.endswith(":") and len(stripped) < 80:
            # не товар, а заголовок (короткая строка с :)
            maybe_item = any(
                x in stripped.lower()
                for x in ("iphone", "ipad", "mac", "watch", "airpod", "gb", "tb", "mm")
            )
            # если похоже на товар (есть серийник в скобках) — это item
            if re.search(r"\([A-Z0-9]{6,}\)", stripped):
                pass  # fall through to item
            elif not maybe_item or stripped.count(" ") <= 4:
                flush()
                header_text = stripped.rstrip(":").strip()
                current_header = normalize_name(header_text)
                i += 1
                continue

        if current_header is None:
            current_header = "Общее"

        item_text = stripped.lstrip("- ").strip()
        if item_text and item_text != "-":
            current_items.append(item_text)
        i += 1

    flush()  # сохраняем и пустые категории
    return categories


def sort_assortment_to_categories(input_text):
    lines = input_text.splitlines()
    return parse_categories(lines)


def _sort_by_memory_and_sim(item_strings):
    """Группировка: объём памяти → тип SIM → алфавит."""
    groups = {}
    for item_str in item_strings:
        sim = detect_sim_type(item_str)
        vol_gb = extract_memory_gb(item_str)
        vol_str = extract_memory(item_str)
        key = (vol_gb, vol_str)
        if key not in groups:
            groups[key] = {"eSIM": [], "SIM+eSIM": [], "SIM": [], "other": []}
        groups[key][sim].append(item_str)

    output = []
    sorted_keys = sorted(
        groups.keys(),
        key=lambda k: (k[0] is None, k[0] if k[0] is not None else float("inf")),
    )
    for vol_gb, vol_str in sorted_keys:
        if vol_str is not None:
            output.append(f"-{vol_str}-")
            output.append("-")
        for sim_type in ["eSIM", "SIM+eSIM", "SIM", "other"]:
            items_list = groups[(vol_gb, vol_str)][sim_type]
            if not items_list:
                continue
            if sim_type != "other":
                output.append(f"-{sim_type}-")
                output.append("-")
            for it in sorted(items_list):
                output.append(it)
                output.append("-")
    return output


def _sort_by_watch_size(item_strings):
    """Группировка часов по размеру корпуса (40/41/42/44/45/46/49 mm)."""
    size_groups = {}
    for item_str in item_strings:
        size = extract_watch_size(item_str)
        size_groups.setdefault(size, []).append(item_str)

    output = []
    sorted_sizes = sorted(
        size_groups.keys(),
        key=lambda s: (s is None, s if s is not None else float("inf")),
    )
    for size in sorted_sizes:
        if size is not None:
            output.append(f"-{size}mm-")
            output.append("-")
        for it in sorted(size_groups[size]):
            output.append(it)
            output.append("-")
    return output


def _sort_plain(item_strings):
    """Простая сортировка с разделителями '-' между позициями."""
    output = []
    for it in sorted(item_strings):
        output.append(it)
        output.append("-")
    return output


def sort_items_in_category(items, header):
    """
    Сортировка товаров внутри категории:
    - часы → по размеру (mm)
    - товары с памятью / SIM → по объёму и типу SIM
    - остальное → алфавит
    Между позициями всегда ставится '-'.
    """
    if items and isinstance(items[0], dict):
        item_strings = [item.get("text", "") for item in items if item.get("text")]
    else:
        item_strings = [str(x) for x in items if str(x).strip()]

    if not item_strings:
        return []

    header_lower = (header or "").lower()

    has_watch_size = any(extract_watch_size(s) is not None for s in item_strings)
    has_memory = any(extract_memory(s) is not None for s in item_strings)
    watch_count = sum(1 for s in item_strings if extract_watch_size(s) is not None)

    is_watch = (
        "watch" in header_lower
        or "ultra" in header_lower and has_watch_size
        or (has_watch_size and watch_count >= max(1, len(item_strings) // 2) and not has_memory)
    )

    is_memory_device = (
        has_memory
        or "iphone" in header_lower
        or "ipad" in header_lower
        or "macbook" in header_lower
        or "mac mini" in header_lower
        or "imac" in header_lower
    )

    if is_watch:
        return _sort_by_watch_size(item_strings)
    if is_memory_device:
        return _sort_by_memory_and_sim(item_strings)
    return _sort_plain(item_strings)


def build_output_text(categories):
    """
    Формат категории:

    ------------
    RayBan:
    ------------
    -
    товар 1
    -
    товар 2
    -

    Пустые категории тоже выводятся (только заголовок).
    """
    output_lines = []
    for cat in categories:
        header = cat.get("header") or cat.get("name")
        if not header:
            continue

        display_header = normalize_name(header)
        if not display_header.endswith(":"):
            display_header += ":"

        dash_len = max(len(display_header) + 2, 12)
        output_lines.append("-" * dash_len)
        output_lines.append(display_header)
        output_lines.append("-" * dash_len)

        items = cat.get("items", [])
        if items:
            sorted_output = sort_items_in_category(items, header)
            # после рамки категории — разделитель '-', затем позиции
            if sorted_output and sorted_output[0] != "-":
                output_lines.append("-")
            output_lines.extend(sorted_output)
        else:
            # пустая категория — оставляем видимой
            output_lines.append("")

        output_lines.append("")  # пустая строка между категориями

    while output_lines and output_lines[-1] == "":
        output_lines.pop()
    return "\n".join(output_lines)


def find_category_for_item(item, categories):
    normalized_item = normalize_name(item)
    normalized_item = normalize_model(normalized_item).lower()
    base = extract_base_name(item).lower()
    for idx, cat in enumerate(categories):
        cat_name = normalize_name(cat["header"]).lower()
        if cat_name.endswith(":"):
            cat_name = cat_name[:-1].strip()
        if cat_name == base:
            return idx
    for idx, cat in enumerate(categories):
        cat_name = normalize_name(cat["header"]).lower()
        if cat_name.endswith(":"):
            cat_name = cat_name[:-1].strip()
        if cat_name and (cat_name in base or base in cat_name):
            return idx
    return None


def add_item_to_categories(item, categories):
    if item.strip().startswith("Б/У -") or item.strip().startswith("Б/У "):
        for idx, cat in enumerate(categories):
            cat_name = normalize_name(cat["header"]).lower()
            if cat_name in ("б/у", "б/у:"):
                categories[idx]["items"].append(item)
                return categories, idx
        new_cat = {"header": "Б/У:", "items": [item]}
        categories.append(new_cat)
        return categories, len(categories) - 1
    idx = find_category_for_item(item, categories)
    if idx is not None:
        categories[idx]["items"].append(item)
        return categories, idx
    else:
        if "iphone" in item.lower():
            base = extract_base_name(item)
            new_header = f"{base}:"
        else:
            if "," in item:
                new_header = item.split(",")[0].strip() + ":"
            else:
                words = item.split()[:2]
                new_header = " ".join(words).strip() + ":"
        new_header = normalize_name(new_header)
        categories.append({"header": new_header, "items": [item]})
        return categories, len(categories) - 1
