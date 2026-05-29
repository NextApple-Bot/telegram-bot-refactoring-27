# bot/utils/sort.py
import re

def normalize_name(name):
    """Нормализует имя, удаляя лишние пробелы."""
    return ' '.join(name.split())

def normalize_model(name):
    """Нормализует название модели, убирая пробел после S."""
    return re.sub(r'S\s+(\d+)', r'S\1', name, flags=re.IGNORECASE)

def extract_memory(text):
    """Извлекает объём памяти из текста (например, 256GB, 512гб, 1TB)."""
    match = re.search(r'(\d+)\s*(gb|гб|tb)', text, re.IGNORECASE)
    if match:
        return f"{match.group(1)}{match.group(2).upper()}"
    return None

def extract_watch_size(text):
    """Извлекает размер часов в мм."""
    match = re.search(r'(\d+)\s*mm', text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None

def detect_sim_type(text):
    """Определяет тип SIM: eSIM, SIM+eSIM или other."""
    lower = text.lower()
    if re.search(r'\(sim\+esim\)|\bsim\+esim\b', lower):
        return 'SIM+eSIM'
    if re.search(r'\(esim\)|\besim\b', lower):
        return 'eSIM'
    return 'other'

def get_full_model_name(item):
    """Возвращает полное название товара без серийных номеров и пометок в скобках."""
    without_brackets = re.sub(r'\([^)]*\)', '', item)
    return normalize_name(without_brackets)

def extract_base_name(item):
    """Возвращает базовое имя товара (модель + память) для определения категории."""
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
    """
    Парсит текст ассортимента в список категорий.
    Поддерживает:
      - старый формат с --- и категорией между ними
      - новый формат: строка дефисов (3+), строка с категорией и двоеточием, строка дефисов
    """
    categories = []
    current_header = None
    current_items = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i].rstrip('\n')
        stripped = line.strip()

        # Пропускаем пустые строки
        if stripped == '':
            i += 1
            continue

        # ===== НОВЫЙ ФОРМАТ: строка дефисов (3 и более) =====
        if re.match(r'^-{3,}$', stripped):
            # Смотрим, что дальше: может быть категория на следующей строке?
            if i + 1 < n and ':' in lines[i+1]:
                # Завершаем предыдущую категорию
                if current_header and current_items:
                    categories.append({"header": current_header, "items": current_items})
                    current_items = []
                # Извлекаем категорию из следующей строки
                header_line = lines[i+1].strip()
                # Убираем возможное двоеточие в конце
                header_text = header_line.rstrip(':').strip()
                current_header = normalize_name(header_text)
                i += 2  # пропускаем разделитель и строку с категорией
                continue
            # Если дальше не категория, просто пропускаем разделитель
            i += 1
            continue

        # ===== СТАРЫЙ ФОРМАТ: разделитель вида -...- с двоеточием внутри =====
        if stripped.startswith('-') and stripped.endswith('-') and ':' in stripped:
            if current_header is not None:
                categories.append({"header": current_header, "items": current_items})
                current_items = []
            header_text = stripped.strip('- ').strip()
            if header_text.endswith(':'):
                header_text = header_text[:-1].strip()
            current_header = normalize_name(header_text)
            i += 1
            continue

        # ===== СТАРЫЙ ФОРМАТ: три строки: ---, категория, --- =====
        if (re.match(r'^\s*-+\s*$', stripped) and
            i + 1 < n and ':' in lines[i+1] and
            i + 2 < n and re.match(r'^\s*-+\s*$', lines[i+2])):
            if current_header is not None:
                categories.append({"header": current_header, "items": current_items})
                current_items = []
            header_line = lines[i+1].strip()
            header_text = header_line.strip('- ').strip()
            if header_text.endswith(':'):
                header_text = header_text[:-1].strip()
            current_header = normalize_name(header_text)
            i += 3
            continue

        # Пропускаем строки, состоящие только из дефисов (запасной вариант)
        if re.match(r'^\s*-+\s*$', stripped):
            i += 1
            continue

        # Пропускаем строки вида "- что-то -" (не товар)
        if re.match(r'^-\s*[^-]+\s*-$', stripped):
            i += 1
            continue

        # Если строка заканчивается на ":" – это может быть категория без разделителя,
        # но у нас уже есть current_header? Обрабатываем аккуратно.
        if stripped.endswith(':'):
            # Если текущей категории нет – начинаем новую
            if current_header is None:
                header_text = stripped.rstrip(':').strip()
                current_header = normalize_name(header_text)
            i += 1
            continue

        # Если нет текущей категории – создаём "Общее:"
        if current_header is None:
            current_header = "Общее:"
            # current_items остаётся пустым

        # Добавляем строку как товар (убираем начальный дефис и пробел, если есть)
        item_text = stripped.lstrip('- ').strip()
        if item_text:  # не пустая строка
            current_items.append(item_text)
        i += 1

    # Добавляем последнюю категорию
    if current_header and current_items:
        categories.append({"header": current_header, "items": current_items})

    return categories

def sort_assortment_to_categories(input_text):
    lines = input_text.splitlines()
    return parse_categories(lines)

# Остальные функции (sort_items_in_category, build_output_text, find_category_for_item, add_item_to_categories)
# оставь без изменений, они не влияют на парсинг входящего ассортимента.
# Но для полноты привожу их полностью (скопируй из своего старого файла, они у тебя есть)
