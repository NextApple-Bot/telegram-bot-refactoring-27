import re
from typing import Dict, List, Any


def normalize_name(name: str) -> str:
    """Нормализация названия (нижний регистр + удаление лишних пробелов)."""
    return " ".join(name.lower().split())


def extract_base_name(text: str) -> str:
    """Извлекает базовое название товара (до первой скобки или спецсимвола)."""
    match = re.match(r'^([^(]+)', text.strip())
    if match:
        return match.group(1).strip()
    return text.strip()


def detect_sim_type(text: str) -> str:
    """Определяет тип SIM-карты по тексту товара."""
    text_lower = text.lower()
    if any(word in text_lower for word in ["esim", "e-sim", "е-сим"]):
        return "eSIM"
    if any(word in text_lower for word in ["nano", "нано"]):
        return "Nano"
    if any(word in text_lower for word in ["dual", "2 sim", "две сим"]):
        return "Dual"
    return "other"


def get_full_model_name(text: str) -> str:
    """Извлекает чистое название модели (до первого пробела или скобки)."""
    match = re.match(r'^([^(]+)', text.strip())
    if match:
        return match.group(1).strip()
    return text.strip()


def build_output_text(categories: List[Dict[str, Any]]) -> str:
    """
    Формирует красивый текстовый вывод ассортимента для отправки в .txt файл.
    """
    lines = []
    lines.append("📦 ТЕКУЩИЙ АССОРТИМЕНТ")
    lines.append("=" * 50)
    lines.append(f"Дата выгрузки: {__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')}\n")

    total_items = 0

    for cat in categories:
        cat_name = cat["name"]
        items = cat.get("items", [])
        
        if not items:
            continue

        lines.append(f"\n🔹 {cat_name} ({len(items)} шт.)")
        lines.append("-" * 40)

        for item in items:
            price_str = f"{item['price']:,} ₽".replace(",", " ") if item.get('price') else "—"
            status = "🔒 ЗАБРОНИРОВАНО" if item.get("is_booked") else "✅ В наличии"
            
            booking_info = f" | {item['booking_info']}" if item.get("booking_info") else ""
            serial = f" | S/N: {item['serial']}" if item.get("serial") else ""

            line = f"• {item['text']}"
            if price_str != "—":
                line += f" — {price_str}"
            line += f"  {status}{booking_info}{serial}"
            lines.append(line)

            total_items += 1

    lines.append("\n" + "=" * 50)
    lines.append(f"Итого товаров: {total_items}")
    lines.append(f"Итого категорий: {len([c for c in categories if c.get('items')])}")

    return "\n".join(lines)


def sort_items_by_name(items: List[Dict]) -> List[Dict]:
    """Сортировка товаров по названию (естественная сортировка)."""
    def natural_key(text: str):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
    
    return sorted(items, key=lambda x: natural_key(x.get("text", "")))


def group_by_model(items: List[Dict]) -> Dict[str, List[Dict]]:
    """Группирует товары по модели (для отчётов по остаткам)."""
    groups = {}
    for item in items:
        model = get_full_model_name(item["text"])
        if model not in groups:
            groups[model] = []
        groups[model].append(item)
    return groups


def sort_assortment_to_categories(content: str) -> List[Dict[str, Any]]:
    """
    Парсит текст ассортимента в список категорий.
    Ожидаемый формат:
    ---
    Категория 1:
    ---
    Товар 1 (SN123)
    Товар 2 (SN456)
    ---
    Категория 2:
    ---
    ...
    """
    if not content or not content.strip():
        return []

    categories = []
    current_category = None
    current_items = []

    lines = [line.strip() for line in content.strip().split('\n') if line.strip()]

    for line in lines:
        if line.startswith('---') or line == '---':
            if current_category and current_items:
                categories.append({
                    "name": current_category,
                    "header": current_category,
                    "items": current_items
                })
            current_category = None
            current_items = []
            continue

        # Если строка похожа на название категории (заканчивается на :)
        part = line.split('(')[0] if '(' in line else line
        if line.endswith(':') and not any(c.isdigit() for c in part):
            if current_category and current_items:
                categories.append({
                    "name": current_category,
                    "header": current_category,
                    "items": current_items
                })
            current_category = line.rstrip(':').strip()
            current_items = []
        else:
            # Это товар
            if current_category is None:
                current_category = "Без категории"
            
            item = {
                "text": line,
                "price": None,
                "is_booked": False,
                "booking_info": None,
                "serial": None
            }
            
            # Пытаемся извлечь серийный номер
            serial_match = re.search(r'\(SN?[:\s-]*([A-Za-z0-9-]+)\)', line, re.IGNORECASE)
