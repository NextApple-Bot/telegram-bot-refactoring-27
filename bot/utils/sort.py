# bot/utils/sort.py
import re


def normalize_name(name):
    return " ".join(str(name).split())


def normalize_model(name):
    return re.sub(r"S\s+(\d+)", r"S\1", name, flags=re.IGNORECASE)


def extract_memory(text):
    """
    Объём накопителя.
    Поддерживает:
      256GB, 1TB, 512 ГБ
      12/256GB, 8/256GB, 12/1TB  (RAM/Storage — берём часть после /)
    """
    if not text:
        return None
    # Сначала формат RAM/Storage: 12/256GB, 8/1TB
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

    # целое без .0
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
    """Объём в GB (число) для сортировки."""
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
    """Размер часов: 40mm … 49mm."""
    if not text:
        return None
    match = re.search(r"(\d{2})\s*mm\b", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def detect_sim_type(text):
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
    return base


def parse_categories(lines):
    """
    Парсит текст ассортимента.
    Пустые категории сохраняются. Порядок категорий = порядок в файле.
    """
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

        # ------------\nHeader:\n------------
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

        # маркеры-разделители -, ----, -256GB- и т.п. — не товары
        if re.match(r"^\s*-+[\w+./]*-?\s*$", stripped) and not re.search(
            r"[А-Яа-яA-Za-z]{4,}", stripped.replace("GB", "").replace("TB", "").replace("mm", "")
        ):
            i += 1
            continue

        if re.match(r"^\s*-+\s*$", stripped):
            i += 1
            continue

        # Header: без рамок (короткая строка)
        if stripped.endswith(":") and len(stripped) < 80:
            if re.search(r"\([A-Z0-9]{6,}\)", stripped):
                pass  # товар
            else:
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

    flush()
    return categories


def sort_assortment_to_categories(input_text):
    return parse_categories(input_text.splitlines())


def _sort_by_memory_and_sim(item_strings):
    """Группировка: объём памяти → тип SIM. Порядок внутри группы — как был."""
    groups = {}
    order_keys = []
    for item_str in item_strings:
        sim = detect_sim_type(item_str)
        vol_gb = extract_memory_gb(item_str)
        vol_str = extract_memory(item_str)
        key = (vol_gb, vol_str)
        if key not in groups:
            groups[key] = {"eSIM": [], "SIM+eSIM": [], "SIM": [], "other": []}
            order_keys.append(key)
        groups[key][sim].append(item_str)

    sorted_keys = sorted(
        groups.keys(),
        key=lambda k: (k[0] is None, k[0] if k[0] is not None else float("inf")),
    )

    output = []
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
            for it in items_list:  # порядок загрузки, без alphabet sort
                output.append(it)
                output.append("-")
    return output


def _sort_by_watch_size(item_strings):
    """Группировка часов по размеру (40/41/42/44/45/46/49 mm)."""
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
        if size is not None:
            output.append(f"-{size}mm-")
            output.append("-")
        for it in size_groups[size]:
            output.append(it)
            output.append("-")
    return output


def _sort_plain(item_strings):
    """Без перестановки — только разделители '-' (категории/порядок неприкасаемы)."""
    output = []
    for it in item_strings:
        output.append(it)
        output.append("-")
    return output


_PHONE_BRANDS = (
    "iphone", "ipad", "macbook", "mac mini", "imac", "ipod",
    "samsung", "galaxy", "huawei", "xiaomi", "redmi", "poco",
    "pixel", "oneplus", "honor", "realme", "oppo", "vivo",
    "nothing", "motorola", "nokia", "sony", "xperia", "asus",
    "rog phone", "zte", "tecno", "infinix",
)


def sort_items_in_category(items, header):
    """
    Сортировка ТОЛЬКО внутри категории (порядок категорий не меняется):
    - часы (Watch в названии или mm у большинства) → по размеру
    - память / телефоны / планшеты → по объёму и SIM
    - остальное → исходный порядок + разделители
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

    # «Ultra» без Watch — это Samsung Ultra и т.п., НЕ часы
    is_watch = (
        "watch" in header_lower
        or (
            has_watch_size
            and watch_count >= max(1, (len(item_strings) + 1) // 2)
            and not has_memory
        )
    )

    is_memory_device = has_memory or any(b in header_lower for b in _PHONE_BRANDS)

    if is_watch:
        return _sort_by_watch_size(item_strings)
    if is_memory_device:
        return _sort_by_memory_and_sim(item_strings)
    return _sort_plain(item_strings)


def build_output_text(categories):
    """
    Формат:

    ------------
    Category:
    ------------
    -
    item
    -

    Пустые категории выводятся. Порядок categories не меняется.
    """
    output_lines = []
    for cat in categories:
        header = cat.get("header") or cat.get("name")
        if not header:
            continue
        # системную не печатаем
        if str(header).strip() == "__SYSTEM__":
            continue

        display_header = normalize_name(header)
        if not display_header.endswith(":"):
            display_header += ":"

        dash_len = max(len(display_header) + 2, 12)
        output_lines.append("-" * dash_len)
        output_lines.append(display_header)
        output_lines.append("-" * dash_len)

        items = cat.get("items", []) or []
        if items:
            sorted_output = sort_items_in_category(items, header)
            if sorted_output and sorted_output[0] != "-":
                output_lines.append("-")
            output_lines.extend(sorted_output)
        else:
            # пустая категория — оставляем как есть
            output_lines.append("")

        output_lines.append("")

    while output_lines and output_lines[-1] == "":
        output_lines.pop()
    return "\n".join(output_lines)


def find_category_for_item(item, categories):
    base = extract_base_name(item).lower()
    for idx, cat in enumerate(categories):
        cat_name = normalize_name(cat["header"]).lower().rstrip(":").strip()
        if cat_name == base:
            return idx
    for idx, cat in enumerate(categories):
        cat_name = normalize_name(cat["header"]).lower().rstrip(":").strip()
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
        categories.append({"header": "Б/У:", "items": [item]})
        return categories, len(categories) - 1

    idx = find_category_for_item(item, categories)
    if idx is not None:
        categories[idx]["items"].append(item)
        return categories, idx

    if "iphone" in item.lower():
        new_header = f"{extract_base_name(item)}:"
    elif "," in item:
        new_header = item.split(",")[0].strip() + ":"
    else:
        new_header = " ".join(item.split()[:2]).strip() + ":"
    new_header = normalize_name(new_header)
    categories.append({"header": new_header, "items": [item]})
    return categories, len(categories) - 1
