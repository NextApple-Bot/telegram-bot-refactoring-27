# Файл: bot/utils/parser.py
import logging
import re
from datetime import datetime

from bot.services.payment_parser import (
    PAYMENT_KEYWORDS,
    extract_payment_amounts,
    extract_prepayments,
)

logger = logging.getLogger(__name__)

PHONE_PATTERN = re.compile(r'(\+?7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}')
# Дата: сначала ищем полную дд.мм.гггг, потом дд.мм
BIRTH_DATE_FULL_PATTERN = re.compile(r'\b(\d{2})\.(\d{2})\.(\d{4})\b')
BIRTH_DATE_SHORT_PATTERN = re.compile(r'(?<!\d)(\d{2})\.(\d{2})(?!\d)')  # не захватываем цифры телефона


def parse_birth_date(text: str) -> str | None:
    # Ищем полную дату
    m = BIRTH_DATE_FULL_PATTERN.search(text)
    if m:
        day, month, year = m.group(1), m.group(2), m.group(3)
        try:
            dt = datetime(int(year), int(month), int(day))
            return dt.strftime("%d.%m.%Y")
        except ValueError:
            pass
    # Ищем короткую дату (день.месяц)
    m = BIRTH_DATE_SHORT_PATTERN.search(text)
    if m:
        day, month = m.group(1), m.group(2)
        try:
            # проверяем, что это корректная дата
            _ = datetime(2000, int(month), int(day))  # год не важен
            return f"{day}.{month}"
        except ValueError:
            pass
    return None


def parse_client_data(text: str) -> dict:
    result = {
        'full_name': None,
        'phones': [],
        'telegram_username': None,
        'social_network': None,
        'referral_source': None,
        'items': [],
        'payments': dict.fromkeys(PAYMENT_KEYWORDS, 0.0),
        'birth_date': None
    }

    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Телефоны
        for match in PHONE_PATTERN.finditer(line):
            full_number = match.group(0)
            clean_phone = re.sub(r'[\s\-\(\)]', '', full_number)
            if clean_phone.startswith('8') or (clean_phone.startswith('7') and not clean_phone.startswith('+7')):
                clean_phone = '+7' + clean_phone[1:]
            if clean_phone not in result['phones']:
                result['phones'].append(clean_phone)

        # Дата рождения (если ещё не нашли)
        if not result['birth_date']:
            birth = parse_birth_date(line)
            if birth:
                result['birth_date'] = birth

        # ФИО
        if not result['full_name']:
            if re.search(r'ФИО|фио|Ф\.И\.О\.', line, re.IGNORECASE):
                parts = line.split(':', 1)
                if len(parts) > 1:
                    result['full_name'] = parts[1].strip()
                else:
                    match = re.search(r'ФИО\s+(.+)', line, re.IGNORECASE)
                    if match:
                        result['full_name'] = match.group(1).strip()
            else:
                words = line.split()
                if 2 <= len(words) <= 4 and all(re.match(r'^[А-ЯЁ][а-яё]*$', w) for w in words):
                    result['full_name'] = line

        # Telegram
        if '@' in line and not result['telegram_username']:
            match = re.search(r'@(\w+)', line)
            if match:
                result['telegram_username'] = match.group(1)

        # Соцсети / площадка
        if re.search(r'соц\s*сети|social|площадка', line, re.IGNORECASE):
            parts = line.split('–', 1)
            if len(parts) > 1:
                result['social_network'] = parts[1].strip()
            else:
                parts = line.split('-', 1)
                if len(parts) > 1:
                    result['social_network'] = parts[1].strip()
                else:
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        result['social_network'] = parts[1].strip()

        # Откуда узнал
        if re.search(r'как\s+о\s+нас\s+узнал|откуда|referral', line, re.IGNORECASE):
            parts = line.split(':', 1)
            if len(parts) > 1:
                result['referral_source'] = parts[1].strip()

        # Товары (с серийниками в скобках)
        if re.search(r'\([A-Z0-9-]{5,}\)', line):
            item_text = line
            price_match = re.search(r'(\d[\d\s]*[.,]?\d*)\s*(?:₽|руб|рублей|р\.?)', line, re.IGNORECASE)
            if price_match:
                price_str = price_match.group(1).replace(' ', '').replace(',', '.')
                try:
                    price = float(price_str)
                except ValueError:
                    price = None
            else:
                price = None
            result['items'].append({'item_text': item_text, 'price': price})

        # Суммы
        payments = extract_payment_amounts(line, ignore_prepay=False)
        for typ, val in payments.items():
            if typ in result['payments']:
                result['payments'][typ] += val
            else:
                result['payments'][typ] = val

    for key in PAYMENT_KEYWORDS:
        if key not in result['payments']:
            result['payments'][key] = 0.0

    result['total'] = sum(result['payments'].values())
    result['main_phone'] = result['phones'][0] if result['phones'] else None

    return result


__all__ = ['parse_client_data', 'extract_payment_amounts', 'extract_prepayments', 'parse_birth_date']
