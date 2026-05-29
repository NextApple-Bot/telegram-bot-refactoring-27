# bot/utils/sort.py
import re

def normalize_name(name):
    return ' '.join(name.split())

def normalize_model(name):
    return re.sub(r'S\s+(\d+)', r'S\1', name, flags=re.IGNORECASE)

def extract_memory(text):
    match = re.search(r'(\d+)\s*(gb|гб|tb)', text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    return None

def extract_watch_size(text):
    match = re.search(r'(\d+)\s*mm', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def detect_sim_type(text):
    lower = text.lower()
    if re.search(r'\(sim\+esim\)|\bsim\+esim\b', lower):
        return 'SIM+eSIM'
    if re.search(r'\(esim\)|\besim\b', lower):
        return 'eSIM'
    return 'other'

def get_full_model_name(item):
    without_brackets = re.sub(r'\([^)]*\)', '', item)
    return normalize_name(without_brackets)

def extract_base_name(item):
    without_brackets = re.sub(r'\([^)]*\)', '', item)
    if ',' in without_brackets:
        model_part = without_brackets.split(',', 1)[0].strip()
    else:
        model_part = without_brackets.strip()
    memory = extract_memory(without_brackets)
    base = f"{model_part} {memory}" if memory else model_part
    base = normalize_name(base)
    base = normalize_model(base)
    return base

def parse_categories(lines):
    categories = []
    current_header = None
    current_items = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].rstrip('\n')
        stripped = line.strip()

        if stripped == '':
            i += 1
            continue

        if re.match(r'^-{3,}$', stripped):
            if i + 1 < n and ':' in lines[i+1]:
                if current_header is not None and current_items:
                    categories.append({"header": current_header, "items": current_items})
                    current_items = []
                header_line = lines[i+1].strip()
                header_text = header_line.rstrip(':').strip()
                current_header = normalize_name(header_text)
                i += 2
                continue
            i += 1
            continue

        if stripped.startswith('-') and stripped.endswith('-') and ':' in stripped:
            if current_header is not None and current_items:
                categories.append({"header": current_header, "items": current_items})
                current_items = []
            header_text = stripped.strip('- ').strip()
            if header_text.endswith(':'):
                header_text = header_text[:-1].strip()
            current_header = normalize_name(header_text)
            i += 1
            continue

        if (re.match(r'^\s*-+\s*$', stripped) and i + 1 < n and ':' in lines[i+1] and i + 2 < n and re.match(r'^\s*-+\s*$', lines[i+2])):
            if current_header is not None and current_items:
                categories.append({"header": current_header, "items": current_items})
                current_items = []
            header_line = lines[i+1].strip()
            header_text = header_line.strip('- ').strip()
            if header_text.endswith(':'):
                header_text = header_text[:-1].strip()
            current_header = normalize_name(header_text)
            i += 3
            continue

        if re.match(r'^\s*-+\s*$', stripped):
            i += 1
            continue

        if re.match(r'^-\s*[^-]+\s*-$', stripped):
            i += 1
            continue

        if stripped.endswith(':'):
            if current_header is None:
                header_text = stripped.rstrip(':').strip()
                current_header = normalize_name(header_text)
            i += 1
            continue

        if current_header is None:
            current_header = "Общее:"

        item_text = stripped.lstrip('- ').strip()
        if item_text:
            current_items.append(item_text)
        i += 1

    if current_header is not None and current_items:
        categories.append({"header": current_header, "items": current_items})

    return categories

def sort_assortment_to_categories(input_text):
    lines = input_text.splitlines()
    return parse_categories(lines)

def sort_items_in_category(items, header):
    if items and isinstance(items[0], dict):
        item_strings = [item.get('text', '') for item in items]
    else:
        item_strings = items[:]

    header_lower = header.lower()
    output = []

    if 'iphone' in header_lower:
        groups = {}
        for item_str in item_strings:
            sim = detect_sim_type(item_str)
            match = re.search(r'(\d+)\s*(gb|tb)', item_str, re.IGNORECASE)
            if match:
                num = int(match.group(1))
                unit = match.group(2).lower()
                vol_gb = num * 1024 if unit == 'tb' else num
                vol_str = f"{num}{unit.upper
